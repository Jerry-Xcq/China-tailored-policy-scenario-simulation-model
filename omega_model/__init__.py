code_version = "2.3.0"
print('loading omega version %s' % code_version)

import os, sys

if 'darwin' in sys.platform:
    os.environ['QT_MAC_WANTS_LAYER'] = '1'

import traceback

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import time

    import pandas as pd
    pd.set_option('chained_assignment', 'raise')
    from pandas.api.types import is_numeric_dtype

    import numpy as np
    np.seterr(all='raise')

    import copy

    from common.omega_globals import *
    from common.omega_types import *
    from common import omega_globals
    from common import file_io, omega_log
    from common.input_validation import *
    from common.omega_functions import *
    from common.omega_eval import *
    from context.context_base_classes import *
    from context.onroad_fuels import *
    from policy.policy_base_classes import *
    from consumer.consumer_base_classes import *
    from producer.producer_base_classes import *

    fueling_classes = OMEGAEnum(['ICE', 'BEV', 'PHEV'])
    ownership_classes = OMEGAEnum(['shared', 'private'])
    legacy_reg_classes = OMEGAEnum(['car', 'truck', 'mediumduty'])
    fuel_units = OMEGAEnum(['gallon', 'kWh'])

    class OMEGASessionSettings(OMEGABase):
        def __init__(self):
            import time

            path = os.path.dirname(os.path.abspath(__file__)) + os.sep
            print(path)
            self.inputfile_metadata = []
            self.session_unique_name = ''
            self.timestamp_str = time.strftime('%Y%m%d_%H%M%S')
            self.start_time = 0
            self.end_time = 0
            self.output_folder_base = 'Final_2_out_china_credit_012_targetmax' + os.sep
            self.output_folder = self.output_folder_base
            self.logfile_prefix = 'o2log_'
            self.logfilename = ''
            self.session_is_reference = True
            self.auto_close_figures = True
            self.save_preliminary_outputs = True
            self.omega_model_path = path
            self.analysis_initial_year = 2026
            self.consolidate_manufacturers = None
            self.manufacturer_gigawatthour_data = None
            self.generate_context_calibration_files = True
            self.context_new_vehicle_generalized_costs_file = None
            self.sales_share_calibration_file = None
            self.vehicles_df = pd.DataFrame()

            self.analysis_final_year = 2031
            self.analysis_dollar_basis = 2022
            self.context_id = 'AEO2023'
            self.context_case_id = 'Reference case'
            self.credit_market_efficiency = 0.01
            self.context_fuel_prices_file = path + 'test_inputs/context_fuel_prices_20231010.csv'
            self.context_electricity_prices_file = path + 'test_inputs/context_electricity_prices_aeo_20231010.csv'
            self.context_new_vehicle_market_file = path + 'test_inputs/context_new_vehicle_market_20230605.csv'
            self.manufacturers_file = path + 'test_inputs/manufacturers_20230928.csv'
            self.market_classes_file = path + 'test_inputs/market_classes_ice_bev_phev-body_style_20230508.csv'
            self.new_vehicle_price_elasticity_of_demand = -1.2
            self.onroad_fuels_file = path + 'test_inputs/onroad_fuels_20240222.csv'
            self.onroad_vehicle_calculations_file = path + 'test_inputs/onroad_vehicle_calculations_LD_20231023.csv'
            self.onroad_vmt_file = path + 'test_inputs/annual_vmt_fixed_by_age_ice_bev_phev-body_style_20230508.csv'
            self.consumer_pricing_multiplier_max = 1.16
            self.consumer_pricing_multiplier_min = 0.9999999996/1.16
            self.producer_generalized_cost_file = path + 'test_inputs/producer_generalized_cost-body_style_20230720.csv'
            self.production_constraints_file = path + 'test_inputs/production_constraints-body_style_20221130_CN_ICE.csv'
            self.sales_share_file = path + 'test_inputs/sales_share_params_China_2025trend_20251226.csv'
            self.vehicle_price_modifications_file = path + 'test_inputs/vehicle_price_modifications-body_style_0kbevincentives_20230720.csv'
            self.vehicle_reregistration_file = path + 'test_inputs/reregistration_fixed_by_age_ice_bev_phev-body_style_20230508.csv'
            self.ice_vehicle_simulation_results_file = path + 'test_inputs/simulated_vehicles_rse_ice_20240226.csv'
            self.bev_vehicle_simulation_results_file = path + 'test_inputs/simulated_vehicles_rse_bev_20231103.csv'
            self.phev_vehicle_simulation_results_file = path + 'test_inputs/simulated_vehicles_rse_phev_20231105.csv'
            self.vehicles_file = path + 'test_inputs/vehicles_ldv_MY2022_20231211_CNmix2025_powertrain_body.csv'
            self.powertrain_cost_input_file = path + 'test_inputs/powertrain_cost_frm_20240221.csv'
            self.glider_cost_input_file = path + 'test_inputs/glider_cost_20220719.csv'
            self.body_styles_file = path + 'test_inputs/body_styles_20220324.csv'
            self.mass_scaling_file = path + 'test_inputs/mass_scaling_20231103.csv'
            self.workfactor_definition_file = path + 'test_inputs/workfactor_definition_20230928.csv'

            self.session_name = 'OMEGA Quick Test'

            self.drive_cycle_weights_file = path + 'test_inputs/drive_cycle_weights_LD_20231023.csv'
            self.drive_cycle_ballast_file = path + 'test_inputs/drive_cycle_ballast_20230104.csv'
            self.drive_cycles_file = path + 'test_inputs/drive_cycles_20230921.csv'
            self.ghg_credit_params_file = path + 'test_inputs/ghg_credit_params_20220301.csv'
            self.ghg_credits_file = path + 'test_inputs/ghg_credits_22trends_20231107_CN_0.csv'
            self.policy_targets_file = path + 'test_inputs/ghg_standards-cm_cn.csv'
            self.nev_requirements_file = path + 'test_inputs/nev_cn_requirements.csv'
            self.offcycle_credits_file = path + 'test_inputs/offcycle_credits_noaction_20231106_CN_0.csv'
            self.fuel_upstream_methods_file = path + 'test_inputs/policy_fuel_upstream_methods-upstream_zero_20210602.csv'
            self.utility_factor_methods_file = path + 'test_inputs/policy_utility_factor_methods_20230517.csv'
            self.policy_fuels_file = path + 'test_inputs/policy_fuels_20230711.csv'
            self.production_multipliers_file = path + 'test_inputs/production_multipliers_20230208.csv'
            self.policy_reg_classes_file = path + 'test_inputs/regulatory_classes_20221019.csv'
            self.required_sales_share_file = path + 'test_inputs/required_sales_share-body_style_noACC2_20230222.csv'

            self.ip_deflators_file = path + 'test_inputs/implicit_price_deflators_20230602.csv'

            self.use_prerun_context_outputs = False
            self.prerun_context_folder = path + 'previous_outputs'
            self.battery_GWh_limit_years = [2025, 2026, 2027, 2028, 2029, 2030]
            self.battery_GWh_limit = [3000, 5000, 8000, 10000, 20000, 20000]
            self.producer_price_modification_scaler = 0.02
            self.producer_footprint_wtp = 200
            self.footprint_min_scaler = 0.9999999996/1.05
            self.footprint_max_scaler = 1.05
            self.redesign_interval_gain_years = [2020, 2025, 2030]
            self.redesign_interval_gain = [1, 0.75, 0.8]
            self.non_context_session_process_scaler = 1
            self.producer_shares_mode = False
            self.producer_compliance_search_multipoint = True
            self.powertrain_cost_with_ira = False
            self.powertrain_cost_with_gpf = False
            self.powertrain_cost_tracker = True
            self.base_year_min_sales = 0
            self.phev_range_mi = 80
            self.bev_of_ice_rlhp60_scaler = 0.85
            self.no_backsliding = True
            self.nmc_share_BEV = {2022: 0.38, 2023: 0.33, 2024: 0.25, 2025: 0.22, 2026: 0.20, 2027: 0.18, 2028: 0.17}
            self.nmc_share_PHEV = {2022: 0.38, 2023: 0.33, 2024: 0.25, 2025: 0.22, 2026: 0.20, 2027: 0.18, 2028: 0.17}
            self.nmc_share_HEV = {2022: 1}
            self.battery_cost_constant_thru = 2025
            self.producer_market_category_ramp_limit = 0.35
            self.producer_strategic_compliance_buffer_years = [2020, 2032, 2033]
            self.producer_strategic_compliance_buffer = [0, 0, 0.001]
            self.relax_second_pass_GWh = True

            self.vehicles_file_base_year_offset = 3
            self.bev_range_mi = 320
            self.bev_mdv_van_range_mi = 180
            self.kwh_per_mile_scale_years = [2020, 2025, 2027, 2029, 2031]
            self.kwh_per_mile_scale = [1.0, 1.0, 0.90, 0.82, 0.80]
            self.rlhp20_min_scaler = 1.0
            self.rlhp20_max_scaler = 1.0
            self.rlhp60_min_scaler = 1.0
            self.rlhp60_max_scaler = 1.0
            self.allow_ice_of_bev = False
            self.phev_battery_kwh = None
            self.force_two_pass = False
            self.include_manufacturers_list = 'all'
            self.exclude_manufacturers_list = 'none'
            self.cost_curve_frontier_affinity_factor = 0.75
            self.slice_tech_combo_cloud_tables = False
            self.verbose = False
            self.iterate_producer_consumer = True
            self.second_pass_production_constraints = False
            self.producer_voluntary_overcompliance = False
            self.flat_context = False
            self.flat_context_year = 2021
            self.run_profiler = False
            self.multiprocessing = True and not self.run_profiler and not getattr(sys, 'frozen', False)

            self.producer_num_market_share_options = 3
            self.producer_num_tech_options_per_ice_vehicle = 3
            self.producer_num_tech_options_per_bev_vehicle = 1
            self.producer_compliance_search_min_share_range = 1e-5
            self.producer_compliance_search_convergence_factor = 0.9
            self.producer_compliance_search_tolerance = 1e-6
            self.producer_voluntary_overcompliance_min_benefit_frac = 0.01
            self.producer_voluntary_overcompliance_min_strategic_compliance_ratio = 0.9999
            self.producer_consumer_max_iterations = 6
            self.producer_consumer_convergence_tolerance = 5e-4
            self.consumer_pricing_num_options = 14
            self.producer_cross_subsidy_price_tolerance = 5e-4

            self.verbose_log_modules = ['producer_compliance_search', 'cross_subsidy_search_',
                                        'cv_cost_curves_', 'v_cost_curves_', 'v_cost_clouds_',
                                        'v_cloud_plots_', 'cv_cloud_plots', 'effects_']

            self.verbose_console_modules = ['producer_compliance_search_',
                                            'p-c_shares_and_costs', 'p-c_max_iterations_',
                                            'cross_subsidy_search_', 'cross_subsidy_multipliers_',
                                            'cross_subsidy_convergence_']

            self.verbose_postproc = ['iteration_']

            self.canary_byvid = -1

            self.log_vehicle_cloud_years = []

            self.log_producer_compliance_search_years = []

            self.log_consumer_iteration_years = [2050]

            self.log_producer_decision_and_response_years = []

            self.plot_and_log_vehicles = []

            self.RegulatoryClasses = None
            self.VehicleTargets = None
            self.OffCycleCredits = None
            self.NEVRequirements = None
            self.Reregistration = None
            self.OnroadVMT = None
            self.SalesShare = None
            self.ProducerGeneralizedCost = None
            self.MarketClass = None
            self.CostCloud = None
            self.PowertrainCost = None
            self.ElectricityPrices = None

            self.notification_destination = None
            self.notification_email = None
            self.notification_password = None

except:
    print("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
    sys.exit(-1)
