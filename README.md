# semg-intent-recognition

Surface-EMG gesture intent recognition — 8-channel MYO armband data, 7 gesture classes.

## Dataset

This project uses the **EMG data for gestures** dataset (also distributed as
`EMG_data_for_gestures`). It is **not** committed to this repository (~251 MB of raw
text); `data/` is listed in `.gitignore`. To reproduce the layout below, download it
from UCI and unpack the contents of `EMG_data_for_gestures-master/` directly into `data/`.

- Source: <https://archive.ics.uci.edu/dataset/481/emg+data+for+gestures>
- DOI: 10.24432/C5GH2K
- License: CC BY 4.0

### Citation

> Lobov, S., Krilova, N., Kastalskiy, I., Kazantsev, V., & Makarov, V. A. (2018).
> Latent Factors Limiting the Performance of sEMG-Interfaces. *Sensors*, 18(4), 1122.
> <https://doi.org/10.3390/s18041122>

### Collection

36 subjects (`01`–`36`), each performing two series of 6–7 static hand gestures. A MYO
Thalmic armband with 8 equally spaced electrodes around the forearm acquired the signals;
data was streamed to a PC over Bluetooth. Each gesture was held 3 s with a 3 s pause
between gestures.

## Layout

```
data/
├── 01/
│   ├── 1_raw_data_13-12_22.03.16.txt
│   └── 2_raw_data_13-13_22.03.16.txt
├── 02/
├── ...
└── 36/
```

Each `*_raw_data_*.txt` is **tab-separated** with a **header row** and 10 columns:

```
time	channel1	channel2	channel3	channel4	channel5	channel6	channel7	channel8	class
1	1e-05	-2e-05	-1e-05	-3e-05	0	-1e-05	0	-1e-05	0
```

| # | Column | Meaning |
|---|--------|---------|
| 1 | `time` | time in ms |
| 2–9 | `channel1`–`channel8` | the eight MYO EMG channels |
| 10 | `class` | gesture label (see below) |

Class labels:

| Label | Gesture |
|-------|---------|
| 0 | unmarked data |
| 1 | hand at rest |
| 2 | hand clenched in a fist |
| 3 | wrist flexion |
| 4 | wrist extension |
| 5 | radial deviation |
| 6 | ulnar deviation |
| 7 | extended palm (not performed by all subjects) |

Class 7 (extended palm) is only present for **subjects 11 and 30**; the other 34 subjects
supply classes 0–6 only. Across the whole dataset the split is heavily skewed toward the
unmarked class — roughly 65% of all samples (~2.7 M of ~4.2 M) are class 0, which covers
the pauses between gestures. Downsampling or explicit class weighting is usually needed.

## Attribution

The dataset description above is adapted from the `README.txt` shipped with the dataset,
which is retained at `data/README.txt`. The dataset is redistributed here under
CC BY 4.0; no modifications were made to the raw files.

## License

Code in this repository is covered by the [LICENSE](LICENSE) file. The dataset in
`data/` is a separate work under CC BY 4.0, as described above.
