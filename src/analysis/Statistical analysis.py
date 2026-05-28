import pandas as pd
import numpy as np
import os
from glob import glob
from scipy import stats
import matplotlib.pyplot as plt

base_path = r"C:\Users\amit0\OneDrive\Desktop\LTP Pulse width"

folders = {
    "20ms": os.path.join(base_path, "Pulse on study (coarse) t = 20ms", "*.xlsx"),
    "40ms": os.path.join(base_path, "Pulse on study (coarse) t = 40ms", "*.xlsx"),
    "60ms": os.path.join(base_path, "Pulse on study (coarse) t = 60ms", "*.xlsx"),
}

all_slopes = {}

# ---------- Extract slope from each run ----------
for condition, pattern in folders.items():

    files = glob(pattern)
    slopes = []

    print(f"Processing {condition}: {len(files)} runs")

    for file in files:

        df = pd.read_excel(file, sheet_name="Raw_Trace")

        # keep rows where resistance was measured
        df = df[df["Resistance (Ohm)"].notna()].copy()
        df.reset_index(drop=True, inplace=True)

        df["Conductance"] = 1 / df["Resistance (Ohm)"]

        G = df["Conductance"]
        G_norm = (G - G.min()) / (G.max() - G.min())

        pulses = np.arange(1, len(G_norm) + 1)

        slope, intercept = np.polyfit(pulses, G_norm, 1)

        slopes.append(slope)

    all_slopes[condition] = slopes

# ---------- Convert to dataframe ----------
slope_df = pd.DataFrame(dict([(k,pd.Series(v)) for k,v in all_slopes.items()]))

print("\nSlopes per run:\n")
print(slope_df)

# ---------- ANOVA ----------
anova = stats.f_oneway(
    slope_df["20ms"].dropna(),
    slope_df["40ms"].dropna(),
    slope_df["60ms"].dropna()
)

print("\nANOVA Results")
print("F-statistic:", anova.statistic)
print("p-value:", anova.pvalue)

# ---------- Save statistics ----------
output_file = os.path.join(base_path, "PulseWidth_correct_statistics.xlsx")

with pd.ExcelWriter(output_file) as writer:

    slope_df.to_excel(writer, sheet_name="Run_Slopes", index=False)

    summary = pd.DataFrame({
        "Condition": ["20ms","40ms","60ms"],
        "Mean_Slope": slope_df.mean(),
        "Std_Slope": slope_df.std()
    })

    summary.to_excel(writer, sheet_name="Summary", index=False)

    anova_df = pd.DataFrame({
        "F_statistic":[anova.statistic],
        "p_value":[anova.pvalue]
    })

    anova_df.to_excel(writer, sheet_name="ANOVA", index=False)

print("\nResults saved to:", output_file)


# ---------- Plot slope comparison ----------
means = slope_df.mean()
stds = slope_df.std()

plt.figure(figsize=(6,5))

plt.bar(means.index, means, yerr=stds, capsize=5)

plt.ylabel("Learning Slope")
plt.xlabel("Pulse Width")
plt.title("Learning Rate vs Pulse Width")

plt.grid(axis='y')

plt.show()
