import time as time_module
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import library
from PyQt5.QtWidgets import QApplication
from lmfit import models, Parameters
from scipy.signal import find_peaks
from scipy.special import loggamma, betaln, gamma

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial"]


def fitter(userinput_dict):
    # CV file reading and data preparation
    print(f"\nReading CV data: {userinput_dict['filename']}")
    cv = library.CV(userinput_dict)
    scan_rate = (cv.dataframe["E"][100] - cv.dataframe["E"][0]) / cv.dataframe["Time"][
        100
    ]

    # preparation of data arrays
    time = np.array(cv.dataframe["Time"])
    potential = np.array(cv.dataframe["E"])
    current = np.array(cv.dataframe["I"])
    transform = library.diff_int(time, current, 1 / 2)

    # setup list of t discontinuities in E'(t) for CPE summation func
    t_discs = [0]
    t_discs.extend(list(cv.t_switch_pot))
    t_discs.append(time[-1])

    def SD_background(x, **params):
        # CPE current
        CPE_current = np.zeros_like(time)
        if any(key.startswith("Q") for key in params):
            # create piecewise constant Q and alpha arrays
            Q_t = library.build_piecewise(time, t_discs, params, "Q")
            alpha_t = library.build_piecewise(time, t_discs, params, "alpha")

            n_seg = len(t_discs) - 1
            k = 1
            while k <= n_seg:
                with np.errstate(
                    invalid="ignore"
                ):  # used to hide unnecessary warnings for t < 0 evaluations
                    # np.where used for termwise Heaviside to prevent NaN values
                    term1 = np.where(
                        time >= t_discs[k - 1],
                        (time - t_discs[k - 1]) ** (1 - alpha_t),
                        0,
                    )
                    term2 = np.where(
                        time >= t_discs[k], (time - t_discs[k]) ** (1 - alpha_t), 0
                    )
                CPE_current += (-1) ** (k + 1) * (term1 - term2)
                k += 1
            CPE_current *= Q_t * scan_rate / gamma(2 - alpha_t)

        # electrolysis
        bkg_electrolysis = np.zeros_like(time)
        if "i0" in params:
            bkg_electrolysis += params["i0"] * np.exp(params["k"] * potential)

        return library.diff_int(time, bkg_electrolysis + CPE_current, 1 / 2)

    # create params for background func
    sign = (
        abs(scan_rate) / scan_rate
    )  # calculate sign for exp init. params based on scan direction
    Q_guess_idx = int(
        0.05 / cv.V_per_index
    )  # find idx of E0 + 50 mV to read current for Q guesses
    Q_guess = abs(current[Q_guess_idx] / scan_rate)
    subset_params = Parameters()
    if userinput_dict["capacitance_model"] != "None":
        counter = 0
        while counter < len(t_discs) - 1:
            subset_params.add(f"Q{counter+1}", value=Q_guess, min=0)
            subset_params.add(f"alpha{counter+1}", value=0.9, min=0.6, max=1)
            counter += 1

    if userinput_dict["bkg_exp"]:
        i0_params = [0, sign * 10]
        k_params = [0, sign * 100]
        subset_params.add(
            "i0", value=sign * 1e-3, min=min(i0_params), max=max(i0_params)
        )
        subset_params.add("k", value=sign * 1e-3, min=min(k_params), max=max(k_params))

    # subset creation
    idx_range1 = int(0.1 / cv.V_per_index)
    idx_range2 = int(0.05 / cv.V_per_index)

    if cv.i_switch_pot.size == 0:
        subset_idx = np.r_[0:idx_range2, len(transform) - idx_range2 : len(transform)]

    if cv.i_switch_pot.size > 0:
        middle_subset = np.empty(0, dtype=int)
        for idx in cv.i_switch_pot:
            middle_subset = np.r_[middle_subset, idx - idx_range2 : idx + idx_range2]
        subset_idx = np.r_[
            0:idx_range1, middle_subset, len(transform) - idx_range2 : len(transform)
        ]
    x_fit = time[subset_idx]
    y_fit = transform[subset_idx]

    def model_subset(x_subset, **params):
        y_full = SD_background(time, **params)
        return y_full[subset_idx]

    # create model and params objects
    subset_model = models.Model(model_subset)

    # perform fit on data subset
    print("Initial fitting on subset of data")
    subset_result = subset_model.fit(
        y_fit, subset_params, x_subset=x_fit, max_nfev=500, method="least_squares"
    )

    # create background model
    model = models.Model(SD_background)
    params = subset_result.params

    # PEAK DETECTION
    if userinput_dict["peak_detection"] == "Automatic":
        bkg = SD_background(time, **params)
        width_param = int(0.03 / cv.V_per_index)
        SD_peaks = library.peak_finder_auto(transform, bkg, width_param)
        print(f"{len(SD_peaks)} peaks detected")

    else:
        SD_peaks = library.peak_finder_manual(cv, transform)

        # prevents fitt.py from continuing while user selecting peaks
        while not library.manual_picking_finished:
            QApplication.processEvents()
            time_module.sleep(0.01)

    # MODEL UPDATE FROM PEAK LIST
    skew_0 = 0
    expon_0 = 1.5
    peak_counter = 0
    for i in SD_peaks:
        try:
            position_guess = cv.dataframe["Time"][i]
            height_guess = transform[i] - model.eval(params, x=time)[i]

            fwhm_guess = 0.09 / abs(scan_rate)
            sigma_guess = (
                fwhm_guess
                * np.arctan2(np.exp(1) * expon_0, skew_0)
                / (np.pi * np.sqrt(2 ** (1 / expon_0) - 1))
            )
            amplitude_guess = (
                sigma_guess
                * height_guess
                / np.exp(
                    2 * (np.real(loggamma(expon_0 + skew_0 * 0.5j)) - loggamma(expon_0))
                    - betaln(expon_0 - 0.5, 0.5)
                    - expon_0 * np.log1p(np.square(skew_0 / (2 * expon_0)))
                    - skew_0 * np.arctan(-skew_0 / (2 * expon_0))
                )
            )
            model += models.Pearson4Model(prefix=f"SD_peak{peak_counter+1}_", time=time)

            params.update(
                models.Pearson4Model(prefix=f"SD_peak{peak_counter+1}_").make_params(
                    sigma=dict(value=sigma_guess),
                    expon=1.5,
                    center=dict(value=position_guess, vary=True),
                    skew=dict(value=skew_0),
                    amplitude=dict(value=amplitude_guess),
                )
            )

            peak_counter += 1
        except:
            pass

    print("Fitting total model")
    result = model.fit(transform, params, x=time, max_nfev=500, method="least_squares")

    # PREPARATION OF DATAFRAMES FOR EXPORTING

    print("Preparing output for reports")
    # filename preparation
    # check for existing files and increment suffix number to prevent overwriting files
    if userinput_dict["name"] == "":
        name = "fitting summary"
    else:
        name = userinput_dict["name"]

    components = result.eval_components()
    df = pd.DataFrame(components)
    df.columns = [col[:-1] if col.endswith("_") else col for col in df.columns]

    df.insert(0, "SD_total_fit", result.best_fit)
    df.insert(0, "SD_current", transform)

    baseline_df = cv.dataframe["Time"].to_frame("Time")
    baseline_df["E"] = cv.dataframe["E"]
    baseline_df["I"] = cv.dataframe["I"]

    for comp in list(components.keys())[::-1]:
        current_comp = library.diff_int(time, components[comp], -1 / 2)
        comp_name = comp.removeprefix("SD_")
        comp_name = comp_name.removesuffix("_")
        df.insert(0, comp_name, current_comp)

    # Baseline creation for each peak
    b_counter = 1
    ip_list = []
    Ep_list = []
    for comp in components:
        if "background" in comp:
            continue
        baseline = result.best_fit - components[comp]
        baseline = library.diff_int(time, baseline, -1 / 2)
        # removes baseline after peak of interest
        idx_p = np.argmax(abs(library.diff_int(time, components[comp], -1 / 2)))
        Ep_list.append(potential[idx_p])
        baseline[idx_p:] = "NaN"
        baseline_df[f"Peak {b_counter} baseline"] = baseline
        ip_list.append(library.diff_int(time, components[comp], -1 / 2)[idx_p])
        b_counter += 1

    df.insert(0, "total_fit", library.diff_int(time, result.best_fit, -1 / 2))
    df.insert(0, "I", cv.dataframe["I"])
    df.insert(0, "E", cv.dataframe["E"])
    df.insert(0, "Time", cv.dataframe["Time"])

    # Summary reports and data outputs
    # CSV
    if userinput_dict["csv"]:
        pd.concat([baseline_df, df.iloc[:, 3:]], axis=1).to_csv(
            f"{userinput_dict['output_dir']}/{name}.csv", index=False
        )

    # XLSX
    if userinput_dict["xlsx"]:
        library.xlsx_summary(userinput_dict, name, df, baseline_df, cv, len(components))

    # PDF
    library.pdf_summary(userinput_dict, name, ip_list, Ep_list, cv, result, baseline_df)

    print(f"Reports saved with name: {name}")
    return "Program ran successfully."
