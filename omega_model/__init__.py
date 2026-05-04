"""

Top-level includes/definitions for the OMEGA model

Defines class OMEGASessionSettings which control an individual simulation session


----

**CODE**

"""

# OMEGA code version number
code_version = "2.3.0"
print('loading omega version %s' % code_version)

import os, sys

if 'darwin' in sys.platform:
    os.environ['QT_MAC_WANTS_LAYER'] = '1'  # for pyqtgraph on MacOS

# CU

import traceback

# 在 omega_model/__init__.py 顶部修改：
import os, sys
# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import time

    import pandas as pd
    # from warnings import simplefilter
    # simplefilter(action="ignore", category=pd.errors.PerformanceWarning)
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

    # --- OMEGA2 global constants ---

    # enumerated values
    fueling_classes = OMEGAEnum(['ICE', 'BEV', 'PHEV'])
    ownership_classes = OMEGAEnum(['shared', 'private'])
    legacy_reg_classes = OMEGAEnum(['car', 'truck', 'mediumduty'])
    fuel_units = OMEGAEnum(['gallon', 'kWh'])

    class OMEGASessionSettings(OMEGABase):
        """
        Define the settings required for a simulation session

        """
        def __init__(self):
            """每次的输入是一个政策场景
            Create an OMEGASessionSettings object with default settings used for testing and development.

            The primary way to create an OMEGASessionSettings object is via the batch process.

            See Also:
                omega_batch.py, producer.vehicle_aggregation.py

            """
            import time
                    #NTR-noIRA

            path = os.path.dirname(os.path.abspath(__file__)) + os.sep #path 的值是当前文件 __init__.py 所在的文件夹的绝对路径，不是上一级目录，而是 omega_model 这个文件夹的路径
            print(path)
            self.inputfile_metadata = []  #输入文件记录: stores information about input files such as filepath, filename and a unique checksum
            self.session_unique_name = ''  #: used by the batch process to give each session within a batch a unique name   OMEGA Final_2 session
            self.timestamp_str = time.strftime('%Y%m%d_%H%M%S')  #: datetime string used to timestamp the session run
            self.start_time = 0  #: used to track session duration
            self.end_time = 0  #: used to track session duration
            self.output_folder_base = 'Final_2_out_china_credit_012_targetmax' + os.sep  #: output folder base name e.g. '2024_01_18_09_32_54_BatchName_SessionName/'
            self.output_folder = self.output_folder_base  #: path to the session output folder
            self.logfile_prefix = 'o2log_'  #: prefix of the session log file name, used in combination with the session unique name
            self.logfilename = ''  #:存储会话日志文件的完整路径名 stores the full filepathname of the session log file
            self.session_is_reference = True  #: = ``True`` if this session is the reference (context) session
            self.auto_close_figures = True  #: auto close postproc figures if ``True``
            self.save_preliminary_outputs = True  #: retains preliminary (i.e. first pass) outputs if ``True``
            self.omega_model_path = path  #: absolute path to the ``omega_model`` directory
            self.analysis_initial_year = 2026  #: stores the analysis initial year, e.g. vehicle base year + 1  这个好像没啥用，因为是识别输入数据中的基准年来确定的起始年
            self.consolidate_manufacturers = None  #这个值将在模型运行时根据信用市场交易效率(credit_market_efficiency)自动确定: run compliance model with a single, consolidated, manufacturer instead of individual manufacturers
            self.manufacturer_gigawatthour_data = None  #: stores first pass total battery GWh consumption by manufacturer for use in limiting second pass GWh
            self.generate_context_calibration_files = True  #会在输出文件夹中创建特定格式的校准数据文件，供后续分析使用: if ``True`` (i.e. ``session_is_reference``) generate context session outputs for use by non-context sessions
            self.context_new_vehicle_generalized_costs_file = None  #: filepathname of the context session new vehicle generalized costs
            self.sales_share_calibration_file = None   #: filepathname of the context session sales share calibration file, if any
            self.vehicles_df = pd.DataFrame()  #: used to store base year vehicle data as a result of vehicle aggregation

            # user context settings:
            self.analysis_final_year = 2031  #: must be >= ``analysis_initial_year``
            # Note that the implicit_price_deflator.csv input file must contain data for this entry:
            self.analysis_dollar_basis = 2022  # 分析输出的"美元年份"，用于比较经通胀/通缩调整后的成本: the 'dollar year' of analysis ouputs, for comparing costs adjusted for inflation/deflation
            self.context_id = 'AEO2023'  #筛选特定情景的燃料价格等: id of the context data used for the context session, e.g. 'AEO2021'
            self.context_case_id = 'Reference case'  #: id of the context sub-case, e.g. 'Reference case', 'High oil price', etc 目前Reference case的数据是用的yn的中国化的
            self.credit_market_efficiency = 0.01  #: 1.0 = 'perfect trading', less than 1.0 implies less than perfect trading of GHG compliance credits, 0.0 implies no trading and all manufacturers must meet their standards using only averaging and banking
            self.context_fuel_prices_file = path + 'test_inputs/context_fuel_prices_20231010.csv'  #: path the context fuel prices file, used by ``context.fuel_prices``
            self.context_electricity_prices_file = path + 'test_inputs/context_electricity_prices_aeo_20231010.csv'  #: path to the context electricity prices file, used by the user-definable ``ElectricityPrices`` class
            self.context_new_vehicle_market_file = path + 'test_inputs/context_new_vehicle_market_20230605.csv'  #: path to the context new vehicle market file, used by the user-definable ``NewVehicleMarket`` class
            self.manufacturers_file = path + 'test_inputs/manufacturers_20230928.csv'  #: path to the manufacturers file, used by ``producer.manufacturers``
            self.market_classes_file = path + 'test_inputs/market_classes_ice_bev_phev-body_style_20230508.csv'  #: path the market class definition file, used by the user-definable ``MarketClass`` class
            self.new_vehicle_price_elasticity_of_demand = -1.2  #价格弹性，即汽车价格变化引起销量变化的比率: indicates change in sales v. change in price at the industry level, used to project action session total sales
            self.onroad_fuels_file = path + 'test_inputs/onroad_fuels_20240222.csv'  #: path to the onroad fuels file, used by ``context.onroad_fuels``
            self.onroad_vehicle_calculations_file = path + 'test_inputs/onroad_vehicle_calculations_LD_20231023.csv'  #: path the onroad vehicle calculations file, used by the ``Vehicle`` class
            self.onroad_vmt_file = path + 'test_inputs/annual_vmt_fixed_by_age_ice_bev_phev-body_style_20230508.csv'  #: path the onroad annual vehicle miles travelled file, used by the user-definable ``OnroadVMT`` class
            self.consumer_pricing_multiplier_max = 1.16  #最多提高5%的价格: maximum market class price multiplier during producer cross-subsidy
            self.consumer_pricing_multiplier_min = 0.9999999996/1.16  #允许最多降低约4.76%的价格: minimum market class price multiplier during producer cross-subsidy (ideally should be ``1/consumer_pricing_multiplier_max``)
            self.producer_generalized_cost_file = path + 'test_inputs/producer_generalized_cost-body_style_20230720.csv'  #: path to the producer generalized cost file, used by the user-definable ``ProducerGeneralizedCost`` class
            self.production_constraints_file = path + 'test_inputs/production_constraints-body_style_20221130_CN_ICE.csv'  #: path to the production constraings file, used by ``context.production_constraints``
            self.sales_share_file = path + 'test_inputs/sales_share_params_China_2025trend_20251226.csv'  #: path to the sales share file, used by the user-definable ``SalesShare`` class
            self.vehicle_price_modifications_file = path + 'test_inputs/vehicle_price_modifications-body_style_0kbevincentives_20230720.csv'  #: path the vehicle price modifications (e.g. 'incentives') file, used by ``context.price_modifications``
            self.vehicle_reregistration_file = path + 'test_inputs/reregistration_fixed_by_age_ice_bev_phev-body_style_20230508.csv'  #: path to the vehicle re-registration file, used by the user-definable ``Reregistration`` class
            self.ice_vehicle_simulation_results_file = path + 'test_inputs/simulated_vehicles_rse_ice_20240226.csv'  #: path the ICE vehicles simulation results file, used by the user-definable ``CostCloud`` class
            self.bev_vehicle_simulation_results_file = path + 'test_inputs/simulated_vehicles_rse_bev_20231103.csv'  #: path the BEV vehicles simulation results file, used by the user-definable ``CostCloud`` class
            self.phev_vehicle_simulation_results_file = path + 'test_inputs/simulated_vehicles_rse_phev_20231105.csv'  #: path the PHEV vehicles simulation results file, used by the user-definable ``CostCloud`` class
            self.vehicles_file = path + 'test_inputs/vehicles_ldv_MY2022_20231211_CNmix2025_powertrain_body.csv'  #: path the base year vehicles file, used by ``producer.vehicle_aggregation``
            self.powertrain_cost_input_file = path + 'test_inputs/powertrain_cost_frm_20240221.csv'  #: path to the power train costs file, used by the user-definable ``PowertrainCost`` class
            self.glider_cost_input_file = path + 'test_inputs/glider_cost_20220719.csv'  #: path the glider cost file, used by ``context.glider_cost``
            self.body_styles_file = path + 'test_inputs/body_styles_20220324.csv'  #: path the body styles file, used by ``context.body_styles``
            self.mass_scaling_file = path + 'test_inputs/mass_scaling_20231103.csv'  #: path the mass scaling file, used by ``context.mass_scaling``
            self.workfactor_definition_file = path + 'test_inputs/workfactor_definition_20230928.csv'  #: path to the workfactor definition file, used by ``policy.workfactor_definition``

            # user session settings:
            self.session_name = 'OMEGA Quick Test'  #: session name string 

            # user policy settings:
            self.drive_cycle_weights_file = path + 'test_inputs/drive_cycle_weights_LD_20231023.csv'  #: path to drive cycle weights file, used by ``policy.drive_cycle_weights``
            self.drive_cycle_ballast_file = path + 'test_inputs/drive_cycle_ballast_20230104.csv'  #: path to drive cycle ballast file, used by ``policy.drive_cycle_ballast``
            self.drive_cycles_file = path + 'test_inputs/drive_cycles_20230921.csv'  #: path to drive cycles file, used by ``policy.drive_cycles``
            self.ghg_credit_params_file = path + 'test_inputs/ghg_credit_params_20220301.csv'  #: path to GHG credit params file, used by ``policy.credit_banking``
            self.ghg_credits_file = path + 'test_inputs/ghg_credits_22trends_20231107_CN_0.csv'  #: path to GHG credits file, used by ``policy.credit_banking``
            self.policy_targets_file = path + 'test_inputs/ghg_standards-cm_cn.csv'  #: path to policy target definitions file, used by user-definable ``VehicleTargets`` class
            self.nev_requirements_file = path + 'test_inputs/nev_cn_requirements.csv'  #: path to NEV credit requirement ratios used during pass 1
            self.offcycle_credits_file = path + 'test_inputs/offcycle_credits_noaction_20231106_CN_0.csv'  #: path to offcycle credits file, used by user-definable ``OffCycleCredits`` class
            self.fuel_upstream_methods_file = path + 'test_inputs/policy_fuel_upstream_methods-upstream_zero_20210602.csv'  #: path to upstream methods file, used by ``policy.upstream_methods``
            self.utility_factor_methods_file = path + 'test_inputs/policy_utility_factor_methods_20230517.csv'  #: path to utility factor methods file, used by ``policy.utility_factors``
            self.policy_fuels_file = path + 'test_inputs/policy_fuels_20230711.csv'  #: path to policy fuels file, used by ``policy.policy_fuels``
            self.production_multipliers_file = path + 'test_inputs/production_multipliers_20230208.csv'  #: path to production multipliers file, used by ``policy.incentives``
            self.policy_reg_classes_file = path + 'test_inputs/regulatory_classes_20221019.csv'  #: path to policy reg classes file, used by user-definable ``RegulatoryClasses`` class
            self.required_sales_share_file = path + 'test_inputs/required_sales_share-body_style_noACC2_20230222.csv'  #: path to required sales share file, used by ``policy.required_sales_share``

            # user postproc settings:
            self.ip_deflators_file = path + 'test_inputs/implicit_price_deflators_20230602.csv'  #: path to implicit price deflators file, used by ``context.ip_deflators``

            # "developer" settings:
            self.use_prerun_context_outputs = False  #: if ``True`` then use context session outputs from a previously run context session
            self.prerun_context_folder = path + 'previous_outputs'  #: path to the previously run context session, if ``use_prerun_context_outputs`` is ``True``
            self.battery_GWh_limit_years = [2025, 2026, 2027, 2028, 2029, 2030]  #: used in combination with ``battery_GWh_limit`` to create industry-level battery production capacity limits year over year
            self.battery_GWh_limit = [3000, 5000, 8000, 10000, 20000, 20000]  #两个参数共同定义了整个行业电池产能的年度上限，应该是后续可以插值: used in combination with ``battery_GWh_limit_years`` to create industry-level battery production capacity limits year over year
            self.producer_price_modification_scaler = 0.02  #设为0表示生产商在计算车辆成本时不考虑补贴: if non-zero then some scalar portion of vehicle incentives (price modifications) are incorporated into the producer vehicle generalized cost
            self.producer_footprint_wtp = 200  #表示生产商估计消费者愿意为每增加一单位车辆尺寸支付的额外费用（200美元）: producer's estimate of consumer willingness to pay for increases in vehicle footprint, used in producer vehicle generalized cost
            self.footprint_min_scaler = 0.9999999996/1.05  #允许车辆尺寸在生产商成本分析中的变化范围: vehicle footprint minimum scaler in producer footprint sweep as part of composite vehicle cost cloud generation
            self.footprint_max_scaler = 1.05  #: vehicle footprint maximum scaler in producer footprint sweep as part of composite vehicle cost cloud generation
            self.redesign_interval_gain_years = [2020, 2025, 2030]  #[2020, 2032, 2033]: used in combination with ``redesign_interval_gain`` to allow modification of vehicle redesign cadence if desired
            self.redesign_interval_gain = [1, 0.75, 0.8]  #[1, 1, 0]：为0时，表示在该年强制进行重新设计: used in combination with ``redesign_interval_gain_years`` to allow modification of vehicle redesign cadence if desired
            self.non_context_session_process_scaler = 1  #: used to modify the number of processes used by non-context sessions when multiprocessing, (e.g. 2 = use 1/2 the default number of processes)
            self.producer_shares_mode = False  #如果为 True，则忽略消费者份额响应: if ``True`` then consumer share response is ignored.  Used for development, troubleshooting, or quicker runtime during testing
            self.producer_compliance_search_multipoint = True  #如果为 True，则生产者合规性搜索会同时从合规点上方和下方逼近（如果可能）: if ``True`` then the producer compliance search will simultaneously approach compliance from points above and below compliance (if possible)
            self.powertrain_cost_with_ira = False  #: if ``True`` then Inflation Reduction Act incentives will apply to powertrain costs
            self.powertrain_cost_with_gpf = False  #如果为 True，则将汽油颗粒过滤器（GPF）成本计入动力系统成本: if ``True`` then gasoline particulate filter costs will apply to powertrain costs
            self.powertrain_cost_tracker = True  #生成详细的动力系统成本输出: if ``True`` then detailed powertrain cost outputs will be generated
            self.base_year_min_sales = 0  #设置基准年车辆销量的最小阈值（例如忽略低销量车辆）: minimum base year vehicles sales threshhold to consider when reading the base year vehicles file (e.g. ignore low-volume vehicles)
            self.phev_range_mi = 80  #设置 PHEV 的目标纯电续航里程（单位：英里）: target PHEV charge-depleting range, miles
            self.bev_of_ice_rlhp60_scaler = 0.85  #设置 BEV 在 60 MPH 时的阻力功率与 ICE 的比例: scaler for BEV roadload horsepower at 60 MPH (BEVs more aerodynamic than their ICE equivalent if scaler < 1.0)
            self.no_backsliding = True  #如果为 True，则 ICE 车辆在重新设计周期中必须保持或改善 CO2e 排放（克/英里）: if ``True`` then ICE vehicles must maintain or improve CO2e g/mi across redesign cycles
            self.nmc_share_BEV = {2022: 0.38, 2023: 0.33, 2024: 0.25, 2025: 0.22, 2026: 0.20, 2027: 0.18, 2028: 0.17}  #: used to define year over year share of BEVs with Nickel Manganese Cobalt battery type
            self.nmc_share_PHEV = {2022: 0.38, 2023: 0.33, 2024: 0.25, 2025: 0.22, 2026: 0.20, 2027: 0.18, 2028: 0.17}  #: used to define year over year share of PHEVs with Nickel Manganese Cobalt battery type
            self.nmc_share_HEV = {2022: 1}  #定义每年 BEV、PHEV 和 HEV 中使用 NMC 电池的比例: used to define year over year share of HEVs with Nickel Manganese Cobalt battery type
            self.battery_cost_constant_thru = 2025  #在此年份之前，电池成本保持不变: hold battery costs constant through this year
            self.producer_market_category_ramp_limit = 0.35  #限制生产者在不同市场类别（如 ICE 和 BEV）之间的销售转换速度，0.2 表示需要 5 年才能完全从一个类别转换到另一个类别: used to constrain producer sales shift between market classes (e.g ICE/BEV).  0.2 => five years to fully switch from one class to another
            self.producer_strategic_compliance_buffer_years = [2020, 2032, 2033]  #: used in combination with ``producer_strategic_compliance_buffer`` to allow manually banking (or burning) GHG credits year over year
            self.producer_strategic_compliance_buffer = [0, 0, 0.001]  #允许生产者在指定年份手动存储或消耗 GHG 信用，2033年有一个非常小的正向缓冲(0.001)，即仅比要求的标准多储备0.1%的信用: used in combination with ``producer_strategic_compliance_buffer_years`` to allow manually banking (or burning) GHG credits year over year
            self.relax_second_pass_GWh = True  #如果为 True，则第二阶段的电池生产量可以超过第一阶段: if ``True`` then second pass battery GWh production may exceed first pass production

            # advanced developer settings:
            self.vehicles_file_base_year_offset = 3  #基准年车辆文件的模型年和重新设计年的偏移量: added to the base year vehicles file model year and prior redesign year
            self.bev_range_mi = 320  #设置 BEV 的目标续航里程: target BEV charge-depleting range, miles
            self.bev_mdv_van_range_mi = 180  #设置中型货车的目标续航里程: target medium-duty van charge-depleting range, miles
            self.kwh_per_mile_scale_years = [2020, 2025, 2027, 2029, 2031]  #可以设置特定年份的效率改进系数，例如设置[2020, 2030]和[1.0, 0.8]表示到2030年效率提高20%: used in combination with ``kwh_per_mile_scale`` to scale BEV kWh/mile consumption values year over year, e.g. simulate improvements over time relative to the original simulation results
            self.kwh_per_mile_scale = [1.0, 1.0, 0.90, 0.82, 0.80]  #: used in combination with ``kwh_per_mile_scale_years`` to scale BEV kWh/mile consumption values year over year, e.g. simulate improvements over time relative to the original simulation results
            self.rlhp20_min_scaler = 1.0  #: minimum roadload horsepower at 20 MPH scaler when sweeping RLHP20
            self.rlhp20_max_scaler = 1.0  #: maximum roadload horsepower at 20 MPH scaler when sweeping RLHP20
            self.rlhp60_min_scaler = 1.0  #: minimum roadload horsepower at 60 MPH scaler when sweeping RLHP60
            self.rlhp60_max_scaler = 1.0  #: maximum roadload horsepower at 60 MPH scaler when sweeping RLHP60
            self.allow_ice_of_bev = False  #若为True，则允许基准年的纯电动车在重新设计时可转为内燃机版本: if ``True`` then base year BEVs will have ICE-equivalent alternative powertrain vehicles available starting at first redesign
            self.phev_battery_kwh = None  #设置 PHEV 电池容量: ``'RSE'`` => use RSE, ``None`` => use range calc, otherwise use scalar value to size PHEV battery capacity
            self.force_two_pass = False  #强制使用两阶段合规性检查: can be used to force two pass (consolidated and non-consolidated compliance passes) as desired
            self.include_manufacturers_list = 'all'  #: ``'all'`` to include all base year vehicle manufacturers, else list of manufacturers to include, e.g. ``['Ford', 'Honda', ...]``
            self.exclude_manufacturers_list = 'none'  #不排除任何制造商: ``'none'`` to include all base year vehicle manufacturers, else list of manufacturers to exclude, e.g. ``['Ferrari', 'Bugatti', ...]``
            self.cost_curve_frontier_affinity_factor = 0.75  #在计算成本云前沿时使用的亲和度因子,值越高，拟合越紧密，前沿上点越多: used in calculation cloud frontiers, lower values generate a more 'approximate' fit to the cloud and a lower number of points on the frontier, higher values generate a tighter fit and generally more points
            self.slice_tech_combo_cloud_tables = False  #: if ``True`` then only save producer search production options data within +- 20% of the target Mg, used in combination with ``log_producer_compliance_search_years`` and ``verbose_log_modules``
            self.verbose = False  #是否启用额外的控制台输出: if ``True`` then enable optional console outputs
            self.iterate_producer_consumer = True  #启用生产者-消费者交叉补贴迭代: enable producer-consumer cross subsidy iteration when ``True``
            self.second_pass_production_constraints = False  #是否在第二阶段应用行业级生产约束: if ``True`` then apply industry-level production constraints on the second pass
            self.producer_voluntary_overcompliance = False  #是否启用生产者自愿超标合规(实验性): enable producer voluntary overcompliance if ``True``, experimental
            self.flat_context = False  #是否将所有上下文值设为固定年份的值(用于故障排除): if ``True`` then all context values are determined by ``flat_context_year`` instead of model year, for troubleshooting
            self.flat_context_year = 2021  #与flat_context结合使用，设置恒定上下文值: used in combination with ``flat_context`` to set constant context values
            self.run_profiler = False  #是否运行性能分析器: run profiler if ``True``
            self.multiprocessing = True and not self.run_profiler and not getattr(sys, 'frozen', False)  #: enables multiprocessing if ``True``

            # search and convergence-related developer settings:
            self.producer_num_market_share_options = 3  #每次生产者合规性搜索迭代中，考虑的市场份额选项的标称数量: nominal number of market share options considered per producer compliance search iteration
            self.producer_num_tech_options_per_ice_vehicle = 3  #: nominal number of tech options per ICE vehicle considered per producer compliance search iteration
            self.producer_num_tech_options_per_bev_vehicle = 1  #: nominal number of tech options per BEV vehicle considered per producer compliance search iteration
            self.producer_compliance_search_min_share_range = 1e-5  # 在生产者合规性搜索迭代中使用的最小份额范围: the minimum share range used during producer compliance search iteration
            self.producer_compliance_search_convergence_factor = 0.9  #用于计算每次迭代的份额范围: producer search share range = ``producer_compliance_search_convergence_factor ** iteration_num``
            self.producer_compliance_search_tolerance = 1e-6  #用于确定生产者合规性搜索是否找到了可接受的解决方案: used to determine if producer compliance search as found an acceptable solution, relative to 1.0 being perfect compliance
            self.producer_voluntary_overcompliance_min_benefit_frac = 0.01  #自愿超额合规的最小收益比例，表示为合规成本的一部分: minimum benefit of voluntary overcompliance, as a fraction of compliance cost, experimental
            self.producer_voluntary_overcompliance_min_strategic_compliance_ratio = 0.9999  #确定考虑的最大自愿超额合规比例: determines the maxinum voluntary overcompliance to consider, experimental
            self.producer_consumer_max_iterations = 6  #生产者-消费者交叉补贴迭代的最大次数: determines the maximum number of producer-consumer cross subsidy iterations to consider
            self.producer_consumer_convergence_tolerance = 5e-4  #确定生产者-消费者份额是否收敛的阈值（绝对市场份额）: the threshhold for determining producer-consumer share convergence, absolute market share
            self.consumer_pricing_num_options = 14  #: the number of cross-subsidy pricing options to consider per cross-subsidy iteration per market class
            self.producer_cross_subsidy_price_tolerance = 5e-4  #确定生产者-消费者价格是否收敛的阈值（: the threshhold for determining producer-consumer price convergence, relative to 1.0 being perfect price convergence

            # logging and verbosity-related settings:
            # list of modules to allow verbose log files, or empty to disable:指定需要生成详细日志文件的模块列表
            self.verbose_log_modules = ['producer_compliance_search', 'cross_subsidy_search_',
                                        'cv_cost_curves_', 'v_cost_curves_', 'v_cost_clouds_',
                                        'v_cloud_plots_', 'cv_cloud_plots', 'effects_']  #: used to enable verbose log file outputs for various modules

            # list of modules to allow verbose console output, or empty to disable指定需要在控制台输出详细信息的模块列表
            self.verbose_console_modules = ['producer_compliance_search_',
                                            'p-c_shares_and_costs', 'p-c_max_iterations_',
                                            'cross_subsidy_search_', 'cross_subsidy_multipliers_',
                                            'cross_subsidy_convergence_']  #: used to enable verbose console outputs for various modules

            self.verbose_postproc = ['iteration_']  #: used to control verbose postproc outputs指定需要在后处理阶段输出详细信息的模块列表

            self.canary_byvid = -1  #: canary base year vehicle ID, for development or troubleshooting指定一个基准年车辆 ID，用于开发或调试

            self.log_vehicle_cloud_years = []  #: = ``'all'`` or list of years to log, empty list to disable logging

            self.log_producer_compliance_search_years = []  #: = ``'all'`` or list of years to log, empty list to disable logging

            self.log_consumer_iteration_years = [2050]  #: = ``'all'`` or list of years to log, empty list to disable logging指定需要记录消费者迭代的年份列表

            self.log_producer_decision_and_response_years = []  #: = ``'all'`` or list of years to log, empty list to disable logging

            self.plot_and_log_vehicles = []  #: list of vehicles to plot in log_producer_compliance_search_years, by namem e.g. ``['ICE Large Van truck minivan 4WD']``

            # dynamic modules / classes提供对用户可定义模块/类的引用
            self.RegulatoryClasses = None  #: reference to user-definable RegulatoryClasses class
            self.VehicleTargets = None  #: reference to user-definable VehicleTargets class
            self.OffCycleCredits = None  #: reference to user-definable OffCycleCredits class
            self.NEVRequirements = None  #: reference to user-definable NEV requirement class
            self.Reregistration = None  #: reference to user-definable Reregistration class
            self.OnroadVMT = None  #: reference to user-definable OnroadVMT class
            self.SalesShare = None  #: reference to user-definable SalesShare class
            self.ProducerGeneralizedCost = None  #: reference to user-definable ProducerGeneralizedCost class
            self.MarketClass = None  #: reference to user-definable MarketClass class
            self.CostCloud = None  #: reference to user-definable CostCloud class
            self.PowertrainCost = None  #: reference to user-definable PowertrainCost class
            self.ElectricityPrices = None  #: reference to user-definable ElectricityPrices class

            self.notification_destination = None  #: for optional text notifications, see ``common.omega_functions.send_text()``
            self.notification_email = None  #: for optional text notifications, see ``common.omega_functions.send_text()``
            self.notification_password = None  #: for optional text notifications, see ``common.omega_functions.send_text()``

except:
    print("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
    sys.exit(-1)
