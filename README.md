# China-tailored policy-scenario simulation model

This repository contains the China-tailored LDV policy simulation model and input data used to support the manuscript:

**Compliance architecture and upstream coupling shape China's vehicle carbon transition**  
Jiarui Xu and Haobing Liu  

The model reconstructs China's light-duty vehicle compliance architecture for the analyses reported in the paper, including CAFC-CO2 target generation, NEV credit requirements, upstream fuel and electricity coupling, manufacturer compliance search, credit banking, credit settlement, and post-processing outputs.

Conceptually informed by the U.S. EPA OMEGA framework; this repository implements a China-tailored reconstruction of policy coupling, target generation and credit-settlement mechanisms for the analyses reported in the paper. The specific reconstruction and design choices are described in the manuscript.

## Repository Contents

```text
.
|-- README.md
|-- CITATION.cff
|-- LICENSE
`-- omega_model/
    |-- omega.py                         # Standalone model entry point
    |-- __init__.py                      # OMEGASessionSettings and default run configuration
    |-- __main__.py                      # Module-level run wrapper
    |-- omega_batch.py                   # Batch-run utilities inherited from the OMEGA workflow
    |-- postproc_session.py              # Session post-processing and figures/tables
    |-- common/                          # Shared utilities, logging, validation and plotting helpers
    |-- consumer/                        # Market classes, sales-share response, stock and VMT modules
    |-- context/                         # Exogenous market, fuel, electricity, cost and vehicle context modules
    |-- policy/                          # CAFC-CO2, NEV, upstream, fuel, credit and regulatory policy modules
    |-- producer/                        # Vehicle aggregation, manufacturers, compliance search and annual data
    `-- test_inputs/                     # Input CSV files used for the manuscript simulations
```

Generated outputs, Python bytecode caches and local IDE settings are intentionally excluded from version control.

## Computing Environment

The manuscript simulations were prepared on:

- Windows 11
- Python 3.11.5 from Anaconda3

The core Python dependencies are:

```text
numpy
pandas
matplotlib
scipy
```

## Installation

Clone or download the repository, then create a clean Python environment:

```bash
conda create -n omega-cn python=3.11.5
conda activate omega-cn
pip install numpy pandas matplotlib scipy
```

No external database is required. The `omega_model/test_inputs/` directory contains the CSV inputs used by the model.

## Running the Model

The current codebase expects the standalone run to be launched from inside `omega_model`:

```bash
cd omega_model
python omega.py
```

The run entry point is `omega_model/omega.py`. The default runtime settings and input-file paths are defined in `OMEGASessionSettings` in `omega_model/__init__.py`. In the workflow notes for the paper, this file may be referred to as `init.py`.

By default, model outputs are written under the configured `output_folder_base` in `omega_model/__init__.py`. The current release configuration uses:

```text
Final_2_out_china_credit_012_targetmax/
```

The output directory contains model logs, input-file metadata, manufacturer annual data, credit-settlement outputs, new-vehicle price outputs and post-processing figures/tables.

## Additional Resource

An interactive project page and web front end for this model are available at:

```text
https://jerry-xcq.github.io/CN_Carbon_Emission_Policy_Simulation_Model/
```

This page is provided for demonstration and exploration.

## Scenario and Tier Mapping

The paper compares policy architecture and upstream-coupling cases through direct changes to the runtime settings and CSV input files.

### Policy A and Policy B

For one model launch, the two policy outputs correspond to the model passes:

- **Policy A**: first-pass result from the model run.
- **Policy B**: second-pass result from the same model run.

With `credit_market_efficiency` set between 0 and 1 in `omega_model/__init__.py`, the model performs a first consolidated pass and a second manufacturer-level pass. The manuscript uses these pass-level outputs to compare the two policy architectures.

### Scenario 1, Scenario 2 and Scenario 3

| Manuscript case | Model configuration |
|---|---|
| Scenario 1 | Default configuration in `omega_model/__init__.py`, using `test_inputs/policy_fuel_upstream_methods-upstream_zero_20210602.csv` with `upstream_zero` and `test_inputs/ghg_standards-cm_cn.csv`. |
| Scenario 2 | Same as Scenario 1, but edit `test_inputs/policy_fuel_upstream_methods-upstream_zero_20210602.csv` so `upstream_calculation_method` is `upstream_actual` instead of `upstream_zero`. |
| Scenario 3 | Same as Scenario 2, but use the tightened CAFC-CO2 standard file `test_inputs/ghg_standards-cm_cn_strict.csv` by changing `policy_targets_file` in `omega_model/__init__.py`. |

The relevant line in the upstream-method file is:

```csv
start_year,upstream_calculation_method
2025,upstream_zero
```

For Scenario 2 and Scenario 3, change it to:

```csv
start_year,upstream_calculation_method
2025,upstream_actual
```

For Scenario 3, change:

```python
self.policy_targets_file = path + 'test_inputs/ghg_standards-cm_cn.csv'
```

to:

```python
self.policy_targets_file = path + 'test_inputs/ghg_standards-cm_cn_strict.csv'
```

### NEV Credit Ratio Requirement Tiers

NEV credit ratio requirements are configured in:

```text
omega_model/test_inputs/nev_cn_requirements.csv
```

The CSV uses the columns:

```csv
model_year,nev_target_ratio
```

Use the following tier values for the manuscript cases:

| Year | normal | pro | max |
|---:|---:|---:|---:|
| 2026 | 0.48 | 0.48 | 0.48 |
| 2027 | 0.58 | 0.58 | 0.58 |
| 2028 | 0.68 | 0.68 | 0.75 |
| 2029 | 0.78 | 0.78 | 0.90 |
| 2030 | 0.85 | 0.88 | 1.05 |
| 2031 | 0.90 | 0.98 | 1.20 |

The included `nev_cn_requirements.csv` currently contains the `max` tier values for 2028-2031. To reproduce the `normal` or `pro` tier, replace the corresponding `nev_target_ratio` values in that file before launching `python omega.py`.

### Upstream Electricity Carbon Factors

Upstream fuel and electricity carbon-emission factors are configured in:

```text
omega_model/test_inputs/policy_fuels_20230711.csv
```

For electricity sensitivity cases, edit the `upstream_co2e_grams_per_unit` values for rows where `fuel_id` is `electricity`.

## Input Data Description

The `omega_model/test_inputs/` directory contains all input data required by the released model configuration. Key groups include:

- Vehicle fleet and simulated vehicle technology data: `vehicles_*`, `simulated_vehicles_rse_*`.
- Market and demand context: `context_new_vehicle_market_*`, `sales_share_params_*`, `market_classes_*`.
- Fuel, electricity and upstream factors: `context_fuel_prices_*`, `context_electricity_prices_*`, `policy_fuels_*`, `policy_fuel_upstream_methods-*`.
- CAFC-CO2 and NEV policy inputs: `ghg_standards-cm_cn.csv`, `ghg_standards-cm_cn_strict.csv`, `nev_cn_requirements.csv`, `ghg_credit_params_*`, `ghg_credits_*`.
- Cost and technology inputs: `powertrain_cost_frm_*`, `glider_cost_*`, `mass_scaling_*`, `producer_generalized_cost-*`.
- Vehicle use, survival and on-road calculations: `annual_vmt_*`, `reregistration_*`, `onroad_fuels_*`, `onroad_vehicle_calculations_*`.

Dates embedded in input filenames are file labels and should not be interpreted as the update dates or data vintages of the underlying inputs. Several input files were updated or China-tailored for the present analysis while retaining the original OMEGA-style filename suffixes, `input_template_name` entries and `input_template_version` entries used by the model's input-validation and run-metadata workflow.

## Reproducibility Notes

- Run scenarios from a clean working tree or archive each scenario configuration before running the next scenario.
- The model writes input-file checksums to each run's metadata output, which should be retained with manuscript reproduction outputs.
- Because the code currently uses intra-package imports such as `common.*`, launch runs from inside `omega_model` using `python omega.py`.
- Output files are intentionally not versioned. Regenerate them from the released code and input files.
- If modifying `omega_model/__init__.py` for scenario runs, record the exact edited lines in a scenario log or commit.

## Citation

The repository includes `CITATION.cff` so GitHub can display citation metadata automatically.

## License

The software code in this repository is released under the MIT License. Input data in `omega_model/test_inputs/` are provided to support scholarly reproduction and reuse subject to any source-specific restrictions. If additional source-specific restrictions are later identified for any input table, document them next to the affected file before publication.
