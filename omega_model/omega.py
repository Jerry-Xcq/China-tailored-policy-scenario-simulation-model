"""

OMEGA top level code

Runs a single session, writes info to log files and the console, executes session post-processing.

----

**CODE**

"""

print('importing %s' % __file__)

import sys, os
from collections import defaultdict

path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(path, '..'))  # picks up omega_model sub-packages

from omega_model import *
from omega_model.consumer import stock, sales_volume

from context.onroad_fuels import OnroadFuel
from context.price_modifications import PriceModifications

import postproc_session


def calc_cross_subsidy_options_and_response(calendar_year, market_class_tree, compliance_id, producer_decision,
                                            cross_subsidy_options_and_response, producer_consumer_iteration_num,
                                            iteration_log, node_name='', verbose=False):
    """
    Traverse the market class tree and generate cross subsidy multipliers and the associated consumer response for
    responsive market categories/classes

    Args:
        calendar_year (int): the year in which the compliance calculations take place
        market_class_tree (dict): a dict of CompositeVehicle object lists hiearchically grouped by market categories
            into market classes
        compliance_id (str): name of manufacturer, e.g. 'consolidated_OEM'
        producer_decision (Series): result of producer compliance search, *without* consumer response
        cross_subsidy_options_and_response (DataFrame, Series): initiall empty dataframe or Series containing cross
            subsidy options and response
        producer_consumer_iteration_num (int): producer-consumer iteration number
        iteration_log (DataFrame): DataFrame of producer-consumer iteration data
        node_name (str): name of the current node
        verbose (bool): enable additional console output if True

    Returns:
        tuple of ``cross_subsidy_options_and_response``, updated ``iteration_log``

    """

    from producer.manufacturers import market_class_data

    children = list(market_class_tree)
    if verbose:
        print('children: %s' % children)

    if node_name:
        cross_subsidy_group = [node_name + '.' + c for c in children]
    else:
        cross_subsidy_group = [c for c in children]

    if all(s in omega_globals.options.MarketClass.responsive_market_categories for s in children):#检查当前节点下的所有子类别是否都属于“响应性市场类别”
        if verbose:
            print('responsive: %s' % cross_subsidy_group)

        if all(mc in market_class_data[compliance_id] for mc in cross_subsidy_group):#如果当前分组是响应性的，并且该制造商生产这个分组中的所有类别
            # search cross subsidy options at this level of the tree
            cross_subsidy_options_and_response, iteration_log = \
                search_cross_subsidies(calendar_year, compliance_id, node_name, cross_subsidy_group,
                                       producer_decision,
                                       cross_subsidy_options_and_response, producer_consumer_iteration_num,
                                       iteration_log)
        elif any(mc in market_class_data[compliance_id] for mc in cross_subsidy_group):#如果当前分组是响应性的，但制造商只生产其中的部分类别
            # only one child available from the manufacturer for this market class (e.g. ICE or BEV-only)
            only_child = [mc for mc in cross_subsidy_group if mc in market_class_data[compliance_id]]
            cross_subsidy_options_and_response = \
                omega_globals.options.SalesShare.calc_shares(calendar_year, compliance_id, producer_decision,
                                                             cross_subsidy_options_and_response, node_name,
                                                             only_child)
            if type(cross_subsidy_options_and_response) is pd.DataFrame:
                cross_subsidy_options_and_response = cross_subsidy_options_and_response.loc[0].copy()
        else:
            pass

    else:
        if verbose:
            print('non-responsive: %s' % cross_subsidy_group)
            # do not search cross-subsidy options at this level of the tree

    for child in market_class_tree:
        if type(market_class_tree[child]) is dict:
            if verbose:
                print('processing child ' + child)
            # process subtree
            cross_subsidy_options_and_response, iteration_log = \
                calc_cross_subsidy_options_and_response(calendar_year, market_class_tree[child], compliance_id,
                                                        producer_decision, cross_subsidy_options_and_response,
                                                        producer_consumer_iteration_num, iteration_log,
                                                        node_name=child, verbose=verbose)

    return cross_subsidy_options_and_response, iteration_log


def logwrite_shares_and_costs(calendar_year, producer_market_classes, share_convergence_error,
                              cross_subsidy_pricing_error, producer_decision_and_response,
                              producer_consumer_iteration_num, cross_subsidy_iteration_num):
    """
    Write detailed producer-consumer cross-subsidy iteration data to the log and console.  For investigation of
    cross-subsidy search behavior.  Optionally called from ``iterate_producer_cross_subsidy()``

    Args:
        calendar_year (int): calendar year of the data
        producer_market_classes (list): list of producer market classes, e.g. ['hauling.ICE', 'hauling.BEV', ...]
        share_convergence_error (float): producer-consumer convergence error
        cross_subsidy_pricing_error (float): cross-subsidy pricing error
        producer_decision_and_response (Series): producer compliance search result with consumer share response
        producer_consumer_iteration_num (int): producer-consumer iteration number
        cross_subsidy_iteration_num (int): cross-subsidy iteration number

    Example:

        ::

            2020 producer / consumer_abs_share_frac_cuv_suv_van.BEV               = 0.001934 / 0.004204 (DELTA:0.002269)
            2020 producer / consumer_abs_share_frac_cuv_suv_van.ICE               = 0.560920 / 0.558651 (DELTA:0.002269)
            2020 producer / consumer_abs_share_frac_pickup.BEV                    = 0.000000 / 0.001080 (DELTA:0.001080)
            2020 producer / consumer_abs_share_frac_pickup.ICE                    = 0.141411 / 0.140331 (DELTA:0.001080)
            2020 producer / consumer_abs_share_frac_sedan_wagon.BEV               = 0.009009 / 0.009009 (DELTA:0.000000)
            2020 producer / consumer_abs_share_frac_sedan_wagon.ICE               = 0.286726 / 0.286726 (DELTA:0.000000)

            cross subsidized price / cost ALT cuv_suv_van.BEV                     $59676 / $54251 R:1.100000
            cross subsidized price / cost ALT cuv_suv_van.ICE                     $34655 / $34696 R:0.998822
            cross subsidized price / cost ALT pickup.BEV                          $69475 / $63159 R:1.100000
            cross subsidized price / cost ALT pickup.ICE                          $40640 / $40689 R:0.998805
            cross subsidized price / cost ALT sedan_wagon.BEV                     $46913 / $46913 R:1.000000
            cross subsidized price / cost ALT sedan_wagon.ICE                     $30698 / $30698 R:1.000000

            modified cross subsidized price / cost ALT cuv_suv_van.BEV            $59676 / $54251 R:1.100000
            modified cross subsidized price / cost ALT cuv_suv_van.ICE            $34655 / $34696 R:0.998822
            modified cross subsidized price / cost ALT pickup.BEV                 $69475 / $63159 R:1.100000
            modified cross subsidized price / cost ALT pickup.ICE                 $40640 / $40689 R:0.998805
            modified cross subsidized price / cost ALT sedan_wagon.BEV            $46913 / $46913 R:1.000000
            modified cross subsidized price / cost ALT sedan_wagon.ICE            $30698 / $30698 R:1.000000

            cross subsidized price / cost ALT BEV                                 $52371 / $50299 R:1.041208
            cross subsidized price / cost ALT ICE                                 $34356 / $34386 R:0.999125
            cross subsidized price / cost ALT cuv_suv_van                         $34842 / $34842 R:0.999999
            cross subsidized price / cost ALT pickup                              $40861 / $40861 R:0.999999
            cross subsidized price / cost ALT sedan_wagon                         $31192 / $31192 R:1.000000
            cross subsidized price / cost ALT TOTAL                               $34613 / $34613 R:0.999999

            2020_0_0  SCORE:0.000296, CE:0.002269, CSPE:0.000001

    """
    omega_log.logwrite('')

    for mc in sorted(producer_market_classes):
        omega_log.logwrite(('%d producer / consumer_abs_share_frac_%s' % (calendar_year, mc)).ljust(70) +
                           '= %.6f / %.6f (DELTA:%.6f)' % (
                               producer_decision_and_response['producer_abs_share_frac_%s' % mc],
                               producer_decision_and_response['consumer_abs_share_frac_%s' % mc],
                               abs(producer_decision_and_response['producer_abs_share_frac_%s' % mc] -
                                   producer_decision_and_response['consumer_abs_share_frac_%s' % mc])
                           ))

    omega_log.logwrite('')

    for mc in sorted(producer_market_classes):
        omega_log.logwrite(
            ('cross subsidized price / cost ALT %s' % mc).ljust(70) + '$%d / $%d R:%f' % (
                producer_decision_and_response['average_ALT_cross_subsidized_price_%s' % mc],
                producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mc],
                producer_decision_and_response['average_ALT_cross_subsidized_price_%s' % mc] /
                producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mc]
            ))

    omega_log.logwrite('')

    for mc in sorted(producer_market_classes):
        omega_log.logwrite(
            ('modified cross subsidized price / cost ALT %s' % mc).ljust(70) + '$%d / $%d R:%f' % (
                producer_decision_and_response['average_ALT_modified_cross_subsidized_price_%s' % mc],
                producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mc],
                producer_decision_and_response['average_ALT_modified_cross_subsidized_price_%s' % mc] /
                producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mc]
            ))

    omega_log.logwrite('')

    for mcat in sorted(omega_globals.options.MarketClass.market_categories):
        try:
            if producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat] > 0:
                omega_log.logwrite(
                    ('cross subsidized price / cost ALT %s' % mcat).ljust(70) + '$%d / $%d R:%f' % (
                        producer_decision_and_response['average_ALT_cross_subsidized_price_%s' % mcat],
                        producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat],
                        producer_decision_and_response['average_ALT_cross_subsidized_price_%s' % mcat] /
                        producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat]
                    ))
        except:
            pass

    omega_log.logwrite(
        'cross subsidized price / cost ALT TOTAL'.ljust(70) + '$%d / $%d R:%f' % (
            producer_decision_and_response['average_ALT_cross_subsidized_price_total'],
            producer_decision_and_response['average_ALT_new_vehicle_mfr_cost'],
            producer_decision_and_response['average_ALT_cross_subsidized_price_total'] /
            producer_decision_and_response['average_ALT_new_vehicle_mfr_cost']
        ))

    omega_log.logwrite('')

    omega_log.logwrite(
        '%d_%d_%d  SCORE:%f, CE:%f, CSPE:%f\n' % (calendar_year, producer_consumer_iteration_num,
                                                  cross_subsidy_iteration_num,
                                                  producer_decision_and_response['pricing_score'],
                                                  share_convergence_error, cross_subsidy_pricing_error))


def update_cross_subsidy_log_data(producer_decision_and_response, calendar_year, compliance_id, converged,
                                  producer_consumer_iteration_num, compliant, share_convergence_error):
    """
    Adds/updates data in the producer decision and response for the given arguments.

    Args:
        producer_decision_and_response (Series): producer decision and cross-subsidy iteration response data
        calendar_year (int): calendar year of the data
        compliance_id (str): manufacturer name, or 'consolidated_OEM'
        converged (bool): ``True`` if producer and consumer market shares are within tolerance
        producer_consumer_iteration_num (int): producer-consumer iteration number
        compliant (bool or None): ``True`` if producer was able to find a compliant production option
        share_convergence_error (float): producer-consumer convergence error

    """
    producer_decision_and_response['calendar_year'] = calendar_year
    producer_decision_and_response['compliance_id'] = compliance_id
    producer_decision_and_response['converged'] = converged * 1
    producer_decision_and_response['producer_consumer_iteration_num'] = producer_consumer_iteration_num
    producer_decision_and_response['compliant'] = compliant
    producer_decision_and_response['share_convergence_error'] = share_convergence_error


# =============================================================================
# NEV 积分补齐相关函数（解决 ICE→BEV/PHEV 克隆导致 nev_credit_per_vehicle 缺失的问题）
# =============================================================================

# 默认 BEV 积分均值（当无法按公式计算时使用）
DEFAULT_BEV_NEV_CREDIT = 0.9


def calc_bev_nev_credit_from_range_mi(range_mi):
    """
    Calculate BEV single-vehicle NEV credit from onroad charge-depleting range (miles).

    根据中国 NEV 积分政策公式计算 BEV 单车积分：
        R_km = range_mi * 1.60934
        S(R): 标准车型积分
            - R < 100 km → 0
            - 100 <= R < 150 km → 0.3
            - R >= 150 km → 0.0017 * R + 0.15, 且 S <= 1.2
        K_range(R): 里程调整系数
            - 100-150 km → 0.7
            - 150-200 km → 0.8
            - 200-300 km → 0.9
            - >= 300 km → 1.0

    Args:
        range_mi (float): onroad charge-depleting range in miles

    Returns:
        float or None: NEV credit per vehicle (rounded to 2 decimal places),
                       or None if range_mi is 0/None/NaN or on any error
    """
    import math

    try:
        # 检查无效输入
        if range_mi is None:
            return None

        # 转为 float，处理各种类型
        try:
            range_mi_float = float(range_mi)
        except (TypeError, ValueError):
            return None

        if math.isnan(range_mi_float) or range_mi_float <= 0:
            return None

        # 英里转公里
        R_km = range_mi_float * 1.60934

        # 计算 S(R): 标准车型积分
        if R_km < 100:
            return 0.0
        elif R_km < 150:
            S = 0.3
        else:
            S = 0.0017 * R_km + 0.15
            S = min(S, 1.2)  # 上限为 1.2

        # 计算 K_range(R): 里程调整系数
        if R_km < 150:
            K_range = 0.7
        elif R_km < 200:
            K_range = 0.8
        elif R_km < 300:
            K_range = 0.9
        else:
            K_range = 1.0

        return round(S * K_range, 2)

    except Exception:
        # 任何异常都返回 None，让调用方决定如何处理
        return None


def resolve_nev_credit_for_oem_year(compliance_id, calendar_year):
    """
    Resolve/recalculate nev_credit_per_vehicle for BEV/PHEV vehicles of a specific OEM and year.

    在 Pass1（第二轮）每个车企每年模拟结束后、存储 NEV 数据前调用，用于：
    1. 对 BEV：如果 nev_credit_per_vehicle == 100（sentinel 值），则按公式用 onroad_charge_depleting_range_mi 计算；
       若 range 仍为 0/None/NaN 或计算出错，则回退为默认均值 DEFAULT_BEV_NEV_CREDIT (0.9)。
       注意：如果里程 <100km 按公式算出 0 分，这是合法结果，不会 fallback。
    2. 对 PHEV：如果 nev_credit_per_vehicle 为 0/None/NaN，则补成 0.5。

    只处理指定 compliance_id 和 calendar_year 的车辆，不影响其他车企/年份的车辆。
    不影响非克隆车辆已经存在的有效 nev_credit_per_vehicle。

    异常保护：任何计算过程中的异常都会被捕获，并使用默认值处理。

    Args:
        compliance_id (str): 车企 ID
        calendar_year (int): 模型年份

    Returns:
        dict: 统计信息 {'bev_recalculated': int, 'bev_fallback': int, 'phev_fixed': int, 'errors': int}
    """
    import math

    stats = {'bev_recalculated': 0, 'bev_fallback': 0, 'phev_fixed': 0, 'errors': 0}

    for veh in omega_globals.finalized_vehicles:
        # 只处理当前车企和年份的车辆
        if getattr(veh, 'compliance_id', None) != compliance_id or getattr(veh, 'model_year', None) != calendar_year:
            continue

        try:
            fueling_class = getattr(veh, 'fueling_class', None)
            credit = getattr(veh, 'nev_credit_per_vehicle', None)

            if fueling_class == 'BEV':
                # 检查是否为 sentinel 值（100 或接近 100）
                try:
                    is_sentinel = credit is not None and abs(float(credit) - 100) < 0.1
                except (TypeError, ValueError):
                    is_sentinel = False

                if is_sentinel:
                    try:
                        range_mi = getattr(veh, 'onroad_charge_depleting_range_mi', 0)
                        calculated_credit = calc_bev_nev_credit_from_range_mi(range_mi)

                        if calculated_credit is not None:
                            # 计算成功（包括 0 分的情况，如里程 <100km）
                            veh.nev_credit_per_vehicle = calculated_credit
                            stats['bev_recalculated'] += 1
                        else:
                            # range 为 0/None/NaN，使用默认均值
                            veh.nev_credit_per_vehicle = DEFAULT_BEV_NEV_CREDIT
                            stats['bev_fallback'] += 1
                    except Exception:
                        # 计算过程出错，使用默认均值
                        veh.nev_credit_per_vehicle = DEFAULT_BEV_NEV_CREDIT
                        stats['bev_fallback'] += 1
                        stats['errors'] += 1

            elif fueling_class == 'PHEV':
                # PHEV：如果 nev_credit_per_vehicle 为 0/None/NaN，补成 0.5
                try:
                    need_fix = (credit is None or
                                (isinstance(credit, float) and math.isnan(credit)) or
                                float(credit) == 0)
                except (TypeError, ValueError):
                    need_fix = True

                if need_fix:
                    veh.nev_credit_per_vehicle = 0.5
                    stats['phev_fixed'] += 1

        except Exception:
            # 整个车辆处理出错，根据 fueling_class 使用默认值
            stats['errors'] += 1
            try:
                fc = getattr(veh, 'fueling_class', None)
                if fc == 'BEV':
                    veh.nev_credit_per_vehicle = DEFAULT_BEV_NEV_CREDIT
                    stats['bev_fallback'] += 1
                elif fc == 'PHEV':
                    veh.nev_credit_per_vehicle = 0.5
                    stats['phev_fixed'] += 1
            except Exception:
                pass  # 无法修复，跳过

    return stats


def _calc_nev_actuals_and_traditional_volume(compliance_id, calendar_year):
    """
    Calculate NEV credit totals and traditional vehicle volume for the given OEM/year.

    使用 fueling_class 来区分 NEV 车和传统车：
    - BEV/PHEV: 计入 nev_actual（按 credits × volume）
    - ICE/HEV/FCV 等其他: 计入 trad_volume

    注意：
    - initial_registered_count 在每年模拟中都会被更新为当年的销量
    - BEV/PHEV 即使 credits = 0（如里程 <100km），也不计入传统车产量

    Args:
        compliance_id (str): manufacturer ID
        calendar_year (int): model year being evaluated

    Returns:
        tuple: (nev_actual, traditional_volume)
    """
    nev_actual = 0.0
    trad_volume = 0.0

    for veh in omega_globals.finalized_vehicles:
        if veh.compliance_id != compliance_id or veh.model_year != calendar_year:
            continue

        fueling_class = getattr(veh, 'fueling_class', None)
        credits = getattr(veh, 'nev_credit_per_vehicle', 0.0) or 0.0
        volume = getattr(veh, 'initial_registered_count', 0.0) or 0.0

        # 使用 fueling_class 判断是否为 NEV 车（BEV/PHEV）
        # 这样即使 credits = 0（如里程 <100km 的 BEV），也不会被当作传统车
        if fueling_class in ('BEV', 'PHEV'):
            nev_actual += credits * volume
        else:
            # ICE, HEV 等其他车型计入传统车产量
            trad_volume += volume

    return nev_actual, trad_volume


# GHG（CAFC-CO2）中国语义处理：使用历史正积分抵扣当前年缺口
def _process_china_ghg_for_year(compliance_id, calendar_year, raw_ghg_credit_Mg, credit_bank):
    """
    Process GHG credits for a single OEM/year using China semantics.

    **China Carryforward Rules:**
    - Credits are discounted by 0.9 per year: effective = original * (0.9 ** age)
    - Credits expire after 3 years (configurable in ghg_credit_params.csv)
    - Oldest credits (soonest to expire) are consumed first

    Args:
        compliance_id (str): OEM ID
        calendar_year (int): current year
        raw_ghg_credit_Mg (float): raw GHG credit = target_Mg - cert_Mg (positive = surplus, negative = deficit)
        credit_bank (CreditBank): the OEM's credit bank

    Returns:
        tuple: (ghg_after_bank, credits_used)
            - ghg_after_bank: GHG balance after using historical credits (may still be negative)
            - credits_used: effective amount of historical credits consumed (Mg, with discount)
    """
    deficit = max(0.0, -raw_ghg_credit_Mg)
    used_from_bank = 0.0

    if deficit > 0:
        # 使用折扣后的有效值抵扣缺口，先到期先用
        used_from_bank = credit_bank.use_positive_credits_Mg(calendar_year, deficit, apply_discount=True)

    ghg_after_bank = raw_ghg_credit_Mg + used_from_bank

    return ghg_after_bank, used_from_bank


def _perform_china_dual_credit_settlement(credit_banks, nev_credit_banks):
    """
    Perform China dual-credit system settlement after all OEMs complete production decisions.

    This function replays every model year sequentially after all OEMs have finished Pass 1 so that:
        * Historical GHG credits are applied year-by-year (oldest first)
        * NEV national clearing is performed for each year using all OEM data
        * Remaining NEV credits can offset CAFC-CO2 deficits
        * Only positive CAFC-CO2 credits are stored (negative deficits do not carry forward)

    **Multiprocessing Support:**
        This function rebuilds required data from ManufacturerAnnualData._data, which is properly
        merged from all subprocess results. This ensures correct operation in both single-process
        and multi-process modes.

    Args:
        credit_banks (dict): {compliance_id: CreditBank}
        nev_credit_banks (dict): {compliance_id: NEVCreditBank}
    """
    from producer.manufacturer_annual_data import ManufacturerAnnualData
    from policy.nev_credit_banking import (
        perform_nev_clearing_for_year,
        perform_nev_cafc_clearing_for_year,
        calc_nev_offset_for_cafc,
        MG_PER_NEV_POINT
    )
    from policy.credit_banking import CreditBank
    from policy.nev_credit_banking import NEVCreditBank

    # =========================================================================
    # 从 ManufacturerAnnualData._data 重建结算所需数据（支持多进程）
    # =========================================================================
    # 在多进程模式下，omega_globals.china_dual_credit_records 不会被正确传递，
    # 但 ManufacturerAnnualData._data 会被正确合并，因此从中重建数据
    china_records = {}
    for mad in ManufacturerAnnualData._data:
        model_year = mad.get('model_year')
        compliance_id = mad.get('compliance_id')
        if model_year is None or compliance_id is None:
            continue
        # 跳过 consolidated_OEM（Pass 0 的数据）
        if compliance_id == 'consolidated_OEM':
            continue

        if model_year not in china_records:
            china_records[model_year] = {}

        target_Mg = mad.get('target_co2e_megagrams', 0.0)
        cert_Mg = mad.get('calendar_year_cert_co2e_megagrams', 0.0)
        raw_ghg_credit = target_Mg - cert_Mg  # 正值=盈余，负值=缺口

        nev_actual = mad.get('nev_actual', 0.0)
        nev_target = mad.get('nev_target', 0.0)
        nev_balance_raw = nev_actual - nev_target

        china_records[model_year][compliance_id] = {
            'target_co2e_megagrams': target_Mg,
            'calendar_year_cert_co2e_megagrams': cert_Mg,
            'raw_ghg_credit': raw_ghg_credit,
            'nev_actual': nev_actual,
            'nev_target': nev_target,
            'nev_balance_raw': nev_balance_raw
        }

    # 如果没有有效数据，直接返回
    if not china_records:
        omega_log.logwrite("\n=== China Dual-Credit Settlement: No data to process ===", echo_console=True)
        return

    omega_log.logwrite("\n=== China Dual-Credit Settlement (Pass 1 Replay) ===", echo_console=True)

    # 初始化CSV数据收集列表
    csv_data_rows = []

    # 重新初始化信用银行（从输入文件恢复初始状态），准备按年份重放
    # 注意：credit_banks 中可能混入了年份键（整数类型）和 'total' 键，需要过滤掉
    # 只保留真正的车企 ID（字符串类型且不是 'total'）
    valid_compliance_ids = [cid for cid in credit_banks.keys() 
                            if isinstance(cid, str) and cid != 'total']
    
    for compliance_id in valid_compliance_ids:
        credit_banks[compliance_id] = CreditBank(
            omega_globals.options.ghg_credit_params_file,
            omega_globals.options.ghg_credits_file,
            compliance_id)

    if nev_credit_banks is None:
        return

    nev_credit_banks.clear()

    all_compliance_ids = set(valid_compliance_ids)

    for cid in all_compliance_ids:
        nev_credit_banks[cid] = NEVCreditBank(cid)

    calendar_years = sorted(china_records.keys())

    for calendar_year in calendar_years:
        omega_log.logwrite("\n--- Year %d ---" % calendar_year, echo_console=True)

        # 更新信用银行年龄（GHG 和 NEV）
        for cid in all_compliance_ids:
            credit_banks[cid].update_credit_age(calendar_year)
            if cid in nev_credit_banks:
                nev_credit_banks[cid].update_credit_age(calendar_year)

        # 重新计算各 OEM 的 nev_balance_before_trade（使用当前 NEV 银行的结转，含折扣）
        year_nev_balances = {}
        for cid in all_compliance_ids:
            record = china_records.get(calendar_year, {}).get(cid, {})
            nev_balance_raw = record.get('nev_balance_raw', 0.0)
            # NEV carry_in 是折扣后的有效值
            carry_in = nev_credit_banks[cid].get_available_credits(calendar_year, apply_discount=True) if cid in nev_credit_banks else 0.0
            balance_before_trade = carry_in + nev_balance_raw
            year_nev_balances[cid] = balance_before_trade
            
            # 如果当年有新的 NEV 正积分，添加到银行
            if nev_balance_raw > 0 and cid in nev_credit_banks:
                nev_credit_banks[cid].add_credit(calendar_year, nev_balance_raw)
            # 更新 ManufacturerAnnualData 以便 perform_nev_clearing_for_year 读取
            ManufacturerAnnualData.update_nev_data(
                calendar_year, cid,
                record.get('nev_actual', 0.0),
                record.get('nev_target', 0.0),
                balance_before_trade,
                overwrite_existing=True
            )

        # =====================================================================
        # Step 1: NEV 全国清算（满足 NEV 比例要求，跨车企交易）
        # =====================================================================
        nev_clearing_results = perform_nev_clearing_for_year(
            calendar_year, ManufacturerAnnualData._data, nev_credit_banks
        )

        # =====================================================================
        # Step 2: 各 OEM 使用历史 GHG 正积分抵扣当年 CAFC-CO2 缺口
        # =====================================================================
        ghg_after_bank_dict = {}  # {compliance_id: ghg_after_bank}
        used_from_bank_dict = {}  # {compliance_id: used_from_bank}
        raw_ghg_credit_dict = {}  # {compliance_id: raw_ghg_credit}
        cafc_deficits_after_bank = {}  # {compliance_id: deficit_Mg}（用于跨车企 NEV-to-CAFC）

        for compliance_id in all_compliance_ids:
            record = china_records.get(calendar_year, {}).get(compliance_id, {})
            raw_ghg_credit = record.get('raw_ghg_credit', 0.0)
            raw_ghg_credit_dict[compliance_id] = raw_ghg_credit

            # 用历史 GHG 正积分抵扣当年缺口
            ghg_after_bank, used_from_bank = _process_china_ghg_for_year(
                compliance_id, calendar_year, raw_ghg_credit,
                credit_banks[compliance_id])

            ghg_after_bank_dict[compliance_id] = ghg_after_bank
            used_from_bank_dict[compliance_id] = used_from_bank
            # 记录使用历史正积分后仍剩余的 CAFC 缺口（正值）
            cafc_deficits_after_bank[compliance_id] = max(0.0, -ghg_after_bank)

        # =====================================================================
        # Step 3: NEV 抵偿 CAFC-CO2 缺口（跨车企交易）
        # 中国现行政策：车企可以购买其他车企的多余 NEV 积分来抵偿本车企的 CAFC-CO2 负积分
        # =====================================================================
        nev_cafc_clearing_results = perform_nev_cafc_clearing_for_year(
            calendar_year, nev_clearing_results, cafc_deficits_after_bank
        )

        # =====================================================================
        # Step 4: 汇总各 OEM 的最终结果
        # =====================================================================
        for compliance_id in all_compliance_ids:
            record = china_records.get(calendar_year, {}).get(compliance_id, {})
            raw_ghg_credit = raw_ghg_credit_dict[compliance_id]
            ghg_after_bank = ghg_after_bank_dict[compliance_id]
            used_from_bank = used_from_bank_dict[compliance_id]

            nev_result = nev_clearing_results.get(compliance_id, {
                'nev_surplus': 0.0,
                'nev_deficit': 0.0,
                'nev_balance_after_trade_nev': 0.0,
                'nev_sold': 0.0,
                'nev_bought': 0.0,
                'remaining_nev_deficit': 0.0,
                'nev_requirement_compliant': True
            })

            nev_cafc_result = nev_cafc_clearing_results.get(compliance_id, {
                'own_nev_used_Mg': 0.0,
                'bought_nev_Mg': 0.0,
                'total_nev_Mg_used': 0.0,
                'remaining_cafc_deficit_Mg': 0.0,
                'remaining_nev_points': 0.0,
                'nev_sold_for_cafc': 0.0
            })

            # NEV 抵偿 CAFC 的总量（本车企 + 购买）
            nev_Mg_used = nev_cafc_result.get('total_nev_Mg_used', 0.0)
            remaining_nev_points = nev_cafc_result.get('remaining_nev_points', 0.0)

            # 最终 GHG 余额（使用历史正积分 + NEV 抵偿后）
            ghg_after_nev = ghg_after_bank + nev_Mg_used
            final_positive_credit = max(0.0, ghg_after_nev)

            # 存入 GHG 银行（只存正积分）
            credit_banks[compliance_id].add_positive_credit_only(calendar_year, final_positive_credit)

            # 更新 NEV 银行（剩余 NEV 正积分可用于下年，消耗已卖出的积分）
            if compliance_id in nev_credit_banks:
                nev_credit_banks[compliance_id].update_balance_after_clearing(remaining_nev_points, calendar_year)

            # 更新合规标记和完整的 GHG 积分流转记录
            ManufacturerAnnualData.update_cafc_nev_results(
                calendar_year, compliance_id,
                raw_ghg_credit=raw_ghg_credit,
                ghg_bank_used=used_from_bank,
                ghg_after_bank=ghg_after_bank,
                ghg_after_nev=ghg_after_nev,
                nev_Mg_used_for_cafc=nev_Mg_used,
                final_positive_credit=final_positive_credit,
                cafc_nev_compliant=(ghg_after_nev >= 0))

            # 日志输出
            nev_actual_val = record.get('nev_actual', 0.0)
            nev_target_val = record.get('nev_target', 0.0)
            own_nev_used = nev_cafc_result.get('own_nev_used_Mg', 0.0)
            bought_nev = nev_cafc_result.get('bought_nev_Mg', 0.0)
            sold_nev_for_cafc = nev_cafc_result.get('nev_sold_for_cafc', 0.0)

            omega_log.logwrite(
                "  %s: GHG[raw=%.1f, bank_used=%.1f, after_bank=%.1f, nev_offset=%.1f(own=%.1f+bought=%.1f), "
                "after_nev=%.1f, stored=%.1f] "
                "NEV[actual=%.1f, target=%.1f, before_trade=%.1f, after_nev_clear=%.1f, sold_for_cafc=%.1f] "
                "Compliant[CAFC=%s, NEV=%s]" %
                (compliance_id,
                 raw_ghg_credit,
                 used_from_bank,
                 ghg_after_bank,
                 nev_Mg_used, own_nev_used, bought_nev,
                 ghg_after_nev,
                 final_positive_credit,
                 nev_actual_val,
                 nev_target_val,
                 year_nev_balances.get(compliance_id, 0.0),
                 nev_result.get('nev_balance_after_trade_nev', 0.0),
                 sold_nev_for_cafc,
                 ghg_after_nev >= 0,
                 nev_result.get('nev_requirement_compliant', True))
            )

            # 收集CSV数据
            # 辅助函数：格式化数值，整数显示为整数，小数保留一位
            def fmt_num(val):
                rounded = round(val, 1)
                if rounded == int(rounded):
                    return int(rounded)
                return rounded

            csv_data_rows.append({
                'Year': calendar_year,
                'Manufacturer': compliance_id,
                'GHG_Raw': fmt_num(raw_ghg_credit),
                'GHG_Bank_Used': fmt_num(used_from_bank),
                'GHG_After_Bank': fmt_num(ghg_after_bank),
                'GHG_NEV_Offset_Total': fmt_num(nev_Mg_used),
                'GHG_NEV_Offset_Own': fmt_num(own_nev_used),
                'GHG_NEV_Offset_Bought': fmt_num(bought_nev),
                'GHG_After_NEV': fmt_num(ghg_after_nev),
                'GHG_Stored': fmt_num(final_positive_credit),
                'NEV_Actual': fmt_num(nev_actual_val),
                'NEV_Target': fmt_num(nev_target_val),
                'NEV_Before_Trade': fmt_num(year_nev_balances.get(compliance_id, 0.0)),
                'NEV_After_Clear': fmt_num(nev_result.get('nev_balance_after_trade_nev', 0.0)),
                'NEV_Sold_For_CAFC': fmt_num(sold_nev_for_cafc),
                'Compliant_CAFC': str(ghg_after_nev >= 0).lower(),
                'Compliant_NEV': str(nev_result.get('nev_requirement_compliant', True)).lower()
            })

            # 更新 NEV 清算结果（添加 CAFC 抵偿相关字段）
            nev_result['own_nev_used_for_cafc_Mg'] = own_nev_used
            nev_result['bought_nev_for_cafc_Mg'] = bought_nev
            nev_result['nev_sold_for_cafc'] = sold_nev_for_cafc
            nev_result['nev_remaining_after_cafc_offset'] = remaining_nev_points  # NEV 抵偿 CAFC 后剩余的 NEV 正积分
            ManufacturerAnnualData.update_nev_clearing_results(calendar_year, compliance_id, nev_result)

    omega_log.logwrite("\n=== China Dual-Credit Settlement Complete ===\n", echo_console=True)

    # 写入双积分结算CSV文件
    if csv_data_rows:
        import csv
        csv_columns = [
            'Year', 'Manufacturer', 'GHG_Raw', 'GHG_Bank_Used', 'GHG_After_Bank',
            'GHG_NEV_Offset_Total', 'GHG_NEV_Offset_Own', 'GHG_NEV_Offset_Bought',
            'GHG_After_NEV', 'GHG_Stored', 'NEV_Actual', 'NEV_Target', 'NEV_Before_Trade',
            'NEV_After_Clear', 'NEV_Sold_For_CAFC', 'Compliant_CAFC', 'Compliant_NEV'
        ]
        csv_file_path = omega_globals.options.output_folder + omega_globals.options.session_unique_name + '_dual_credit_settlement.csv'
        try:
            with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
                writer.writeheader()
                writer.writerows(csv_data_rows)
        except Exception as e:
            omega_log.logwrite("Warning: Failed to write dual credit settlement CSV: %s" % str(e), echo_console=True)


def run_compliance_id(compliance_id, pass_num, cumulative_battery_GWh, credit_banks, manufacturer_annual_data_table,
                      iteration_log, nev_credit_banks=None):
    from producer import compliance_search
    from policy.credit_banking import CreditBank
    from policy.nev_credit_banking import NEVCreditBank
    from producer.vehicle_annual_data import VehicleAnnualData
    from producer.manufacturer_annual_data import ManufacturerAnnualData
    from context.new_vehicle_market import NewVehicleMarket

    if pass_num > 0:
        omega_log.init_logfile(compliance_id)
        omega_globals.cumulative_battery_GWh = cumulative_battery_GWh
        omega_globals.options.multiprocessing = False
        omega_globals.pass_num = pass_num  # 同步 pass_num 到子进程，确保 second_pass_production_constraints 逻辑正确

    omega_log.logwrite("\nRunning %s Pass %d: Manufacturer=%s" % (omega_globals.options.session_unique_name,
                                                                  pass_num, compliance_id),
                       echo_console=True)
    analysis_end_year = omega_globals.options.analysis_final_year + 1
    credit_banks[compliance_id] = CreditBank(
        omega_globals.options.ghg_credit_params_file,
        omega_globals.options.ghg_credits_file, compliance_id)
    if nev_credit_banks is not None and compliance_id not in nev_credit_banks:
        nev_credit_banks[compliance_id] = NEVCreditBank(compliance_id)
    prior_producer_decision_and_response = None
    for calendar_year in range(omega_globals.options.analysis_initial_year, analysis_end_year):

        credit_banks[compliance_id].update_credit_age(calendar_year)

        if manufacturer_annual_data_table is None or omega_globals.options.credit_market_efficiency == 0.0:
            # strategy: use credits and pay debits over their remaining lifetime, instead of all at once:
            strategic_target_offset_Mg = 0
            current_credits, current_debits = credit_banks[compliance_id].get_credit_info(calendar_year)
            for c in current_credits + current_debits:
                if c.model_year < omega_globals.options.analysis_initial_year:
                    # allow some strategic under-compliance for historical credits
                    if c.remaining_balance_Mg < 0 or omega_globals.options.credit_market_efficiency != 0.0:
                        strategic_target_offset_Mg += \
                            c.remaining_balance_Mg * (1 / max(1, c.remaining_years - 1))
                else:
                    # don't allow strategic under-compliance for analysis year credits
                    strategic_target_offset_Mg += \
                        min(0, c.remaining_balance_Mg) * (1 / max(1, c.remaining_years - 1))
        else:
            strategic_target_offset_Mg = \
                manufacturer_annual_data_table[(manufacturer_annual_data_table['compliance_id'] == compliance_id) &
                                               (manufacturer_annual_data_table['model_year'] == calendar_year)][
                    'strategic_offset'].item()

        producer_decision_and_response = None
        best_winning_combo_with_sales_response = None
        omega_globals.locked_price_modification_data = dict()

        producer_consumer_iteration_num = 0
        iterate_producer_consumer = True

        while iterate_producer_consumer:
            omega_log.logwrite("Running %s:  Year=%s  Iteration=%s %s" %
                               (omega_globals.options.session_unique_name, calendar_year,
                                producer_consumer_iteration_num, compliance_id),
                               echo_console=True)

            candidate_mfr_composite_vehicles, pre_production_vehicles, producer_decision, market_class_tree, \
                producer_compliant, GWh_limit = \
                compliance_search.search_production_options(compliance_id, calendar_year,
                                                            producer_decision_and_response,
                                                            producer_consumer_iteration_num,
                                                            strategic_target_offset_Mg,
                                                            prior_producer_decision_and_response)

            # if producer_compliant is None:
            #     omega_log.logwrite('%%%%%% Production Constraints Violated ... %%%%%%')

            # composite vehicles have been updated from producer_decision at this point
            producer_market_classes = \
                calc_market_class_data_from_composite_vehicles(candidate_mfr_composite_vehicles, producer_decision)#计算9种类别的加权属性

            calc_market_data_from_sales(candidate_mfr_composite_vehicles, producer_decision)#计算两个类别层级的属性和销量等

            if 'producer_compliance_search' in omega_globals.options.verbose_console_modules:
                for mc in sorted(omega_globals.options.MarketClass.market_classes):
                    if 'producer_abs_share_frac_%s' % mc in producer_decision:
                        omega_log.logwrite(
                            ('%d producer_abs_share_frac_%s' % (calendar_year, mc)).ljust(50) + '= %.6f' %
                            (producer_decision['producer_abs_share_frac_%s' % mc]))
                omega_log.logwrite('')

            best_winning_combo_with_sales_response, iteration_log, producer_decision_and_response = \
                iterate_producer_cross_subsidy(calendar_year, compliance_id, best_winning_combo_with_sales_response,
                                               candidate_mfr_composite_vehicles, iteration_log,
                                               producer_consumer_iteration_num, producer_market_classes,
                                               producer_decision, strategic_target_offset_Mg)

            converged, share_convergence_error, cross_subsidy_pricing_error = \
                detect_producer_consumer_convergence(producer_decision_and_response, producer_market_classes)

            # decide whether to continue iterating or not
            iterate_producer_consumer = omega_globals.options.iterate_producer_consumer \
                                        and producer_consumer_iteration_num < \
                                        omega_globals.options.producer_consumer_max_iterations \
                                        and (not converged or producer_decision_and_response['total_battery_GWh']
                                             > GWh_limit)

            if iterate_producer_consumer:
                producer_consumer_iteration_num += 1
            else:
                if producer_consumer_iteration_num >= omega_globals.options.producer_consumer_max_iterations:
                    if 'p-c_max_iterations' in omega_globals.options.verbose_console_modules:
                        omega_log.logwrite(
                            'PRODUCER-CONSUMER MAX ITERATIONS EXCEEDED, ROLLING BACK TO BEST ITERATION',
                            echo_console=True)
                    producer_decision_and_response = best_winning_combo_with_sales_response

        update_cross_subsidy_log_data(producer_decision_and_response, calendar_year, compliance_id, converged,
                                      producer_consumer_iteration_num, producer_compliant, share_convergence_error)

        producer_decision_and_response['cross_subsidy_iteration_num'] = -10  # tag final result

        iteration_log.append(producer_decision_and_response)

        total_credits_co2e_megagrams, production_battery_gigawatthours = \
            compliance_search.finalize_production(calendar_year, compliance_id,
                                                  candidate_mfr_composite_vehicles,
                                                  pre_production_vehicles,
                                                  producer_decision_and_response)

        # Pass 1 with NEV: 计算并存储 NEV 数据到 ManufacturerAnnualData
        # 注意：不再使用 china_dual_credit_records，结算时直接从 ManufacturerAnnualData 重建数据
        # 这样可以支持多进程模式（ManufacturerAnnualData._data 会被正确合并）
        if pass_num > 0 and nev_credit_banks is not None and omega_globals.options.NEVRequirements:
            # 在计算 NEV 积分前，先补齐/重算本车企本年克隆车辆的 nev_credit_per_vehicle
            # 这样存入 ManufacturerAnnualData 的 nev_actual 就是正确的值
            resolve_nev_credit_for_oem_year(compliance_id, calendar_year)
            nev_actual, trad_volume = _calc_nev_actuals_and_traditional_volume(compliance_id, calendar_year)
            nev_target_ratio = omega_globals.options.NEVRequirements.get_target_ratio(calendar_year)
            nev_target = nev_target_ratio * trad_volume
            nev_balance_raw = nev_actual - nev_target
            # 存储到 ManufacturerAnnualData，供后续双积分结算使用
            # nev_balance_before_trade 字段暂时存储 nev_balance_raw，真正的结转逻辑在 replay 阶段处理
            ManufacturerAnnualData.update_nev_data(calendar_year, compliance_id,
                                                   nev_actual, nev_target, nev_balance_raw)

        if pass_num == 0:
            omega_globals.cumulative_battery_GWh['total'] += production_battery_gigawatthours
            omega_globals.cumulative_battery_GWh[calendar_year] = omega_globals.cumulative_battery_GWh['total']

        # Pass 0: 使用原有 EPA 语义的 handle_credit
        # Pass 1 with NEV: 暂存数据，稍后统一在中国双积分结算中处理
        if pass_num == 0 or nev_credit_banks is None or not omega_globals.options.NEVRequirements:
            credit_banks[compliance_id].handle_credit(calendar_year, total_credits_co2e_megagrams)  # CU RV

        omega_globals.options.SalesShare.store_producer_decision_and_response(producer_decision_and_response)

        stock.update_stock(calendar_year, compliance_id)

        prior_producer_decision_and_response = producer_decision_and_response

    credit_banks[compliance_id].credit_bank.to_csv(omega_globals.options.output_folder +
                                                   omega_globals.options.session_unique_name +
                                                   ' %s GHG_credit_balances.csv' % compliance_id,
                                                   columns=sorted(credit_banks[compliance_id].credit_bank.columns),
                                                   index=False)

    credit_banks[compliance_id].transaction_log.to_csv(
        omega_globals.options.output_folder + omega_globals.options.session_unique_name +
        ' %s GHG_credit_transactions.csv' % compliance_id,
        columns=sorted(credit_banks[compliance_id].transaction_log.columns), index=False)

    finalized_vehicles = [v for v in omega_globals.finalized_vehicles if v.compliance_id == compliance_id and
                          v.model_year >= omega_globals.options.analysis_initial_year]

    vehicle_annual_data = [vad for vad in VehicleAnnualData._data
                           if vad['compliance_id'] == compliance_id and
                           vad['calendar_year'] >= omega_globals.options.analysis_initial_year]

    manufacturer_annual_data = [mad for mad in ManufacturerAnnualData._data
                                if mad['compliance_id'] == compliance_id and
                                mad['model_year'] >= omega_globals.options.analysis_initial_year]

    context_new_vehicle_generalized_costs = NewVehicleMarket._context_new_vehicle_generalized_costs

    session_new_vehicle_generalized_costs = NewVehicleMarket._session_new_vehicle_generalized_costs

    cost_tracker = dict()
    for k, v in omega_globals.options.PowertrainCost.cost_tracker.items():
        if v['compliance_id'] == compliance_id:
            cost_tracker[k] = v

    return (compliance_id, finalized_vehicles, credit_banks, iteration_log, vehicle_annual_data,
            manufacturer_annual_data, context_new_vehicle_generalized_costs, session_new_vehicle_generalized_costs,
            cost_tracker)


def run_producer_consumer(pass_num, manufacturer_annual_data_table):
    """
    Create producer cost-minimizing technology and market share options, in consideration of market response from
    the consumer, possibly with iteration between the two. Iterates across years for each compliance ID.  When
    consolidating manufacturers, the compliance ID is 'consolidated_OEM', otherwise the compliance ID is the
    manufacturer name.

    Args:
        pass_num (int): the pass number, 0 = first, 1 = second, etc.
        manufacturer_annual_data_table (None, or DataFrame): if provided, contains manufacturer-level data from the
        first pass

    Returns:
         Iteration log dataframe, dict of credit bank information (iteration_log, credit_banks),
         updates omega data with final vehicle technology and market share data

    """
    from producer.vehicles import Vehicle
    from producer.vehicle_annual_data import VehicleAnnualData
    from producer.manufacturer_annual_data import ManufacturerAnnualData
    from context.new_vehicle_market import NewVehicleMarket

    iteration_log = []

    credit_banks = dict()
    nev_credit_banks = dict() if (pass_num > 0 and omega_globals.options.NEVRequirements) else None

    # 注意：不再初始化 omega_globals.china_dual_credit_records
    # 双积分结算时直接从 ManufacturerAnnualData._data 重建数据（支持多进程）

    if omega_globals.options.multiprocessing and pass_num > 0:
        results = []
        for compliance_id in Vehicle.compliance_ids:
            results.append(omega_globals.pool.apply_async(func=run_compliance_id,
                                                          args=[compliance_id, pass_num,
                                                                omega_globals.cumulative_battery_GWh, credit_banks,
                                                                manufacturer_annual_data_table, iteration_log,
                                                                nev_credit_banks],
                                                          callback=None,
                                                          error_callback=error_callback))

        compliance_id_results = sorted([r.get() for r in results])

        for (compliance_id, cid_finalized_vehicles, cid_credit_bank, cid_iteration_log, cid_vehicle_annual_data,
             cid_manufacturer_annual_data, cid_context_new_vehicle_generalized_costs,
             cid_session_new_vehicle_generalized_costs, cid_cost_tracker) in compliance_id_results:

            cid_finalized_vehicles.sort()
            omega_globals.finalized_vehicles.extend(cid_finalized_vehicles)

            # update credit banks
            credit_banks.update(cid_credit_bank)

            # update iteration_log
            iteration_log.extend(cid_iteration_log)

            # update VehicleAnnualData
            VehicleAnnualData._data.extend(cid_vehicle_annual_data)

            # update manufacturer annual data
            ManufacturerAnnualData._data.extend(cid_manufacturer_annual_data)

            # update vehicle generalized cost data
            NewVehicleMarket._context_new_vehicle_generalized_costs.update(cid_context_new_vehicle_generalized_costs)
            NewVehicleMarket._session_new_vehicle_generalized_costs.update(cid_session_new_vehicle_generalized_costs)

            # update cost tracker data
            omega_globals.options.PowertrainCost.cost_tracker.update(cid_cost_tracker)

    else:
        for compliance_id in Vehicle.compliance_ids: #如果是不合并生产商则是遍历所有车企
            run_compliance_id(compliance_id, pass_num, omega_globals.cumulative_battery_GWh, credit_banks,
                              manufacturer_annual_data_table, iteration_log, nev_credit_banks)

    # =====================================================================
    # Pass 1: NEV 清算 + NEV 抵偿 CAFC-CO2 + 中国版 CreditBank 处理
    # =====================================================================
    if pass_num > 0 and nev_credit_banks is not None and omega_globals.options.NEVRequirements:
        # 注意：克隆车辆的 nev_credit_per_vehicle 已经在每个车企每年的 run_compliance_id 中处理过了
        # （在 _calc_nev_actuals_and_traditional_volume 之前调用 resolve_nev_credit_for_oem_year）
        _perform_china_dual_credit_settlement(credit_banks, nev_credit_banks)

    iteration_log_df = pd.DataFrame(iteration_log)

    iteration_log_df = iteration_log_df.drop_duplicates()

    iteration_log_df.to_csv(
        omega_globals.options.output_folder + omega_globals.options.session_unique_name +
        '_producer_consumer_iteration_log.csv', columns=sorted(iteration_log_df.columns))

    return iteration_log_df, credit_banks


def calc_cross_subsidy_metrics(mcat, cross_subsidy_group, producer_decision, cross_subsidy_options_and_response):
    """
    Calculate cross-subsidy metrics (prices and share deltas).
    这个函数在交叉补贴的搜索循环中扮演着**“裁判员”的角色。在 create_cross_subsidy_options 生成了一系列价格方案，并且 SalesShare.calc_shares 计算出了消费者对这些价格的反应之后，此函数被调用
    Args:
        mcat (str): market category, e.g. 'hauling' / 'non_hauling'
        cross_subsidy_group (list): list of cross-subsidized market classes, e.g. ['hauling.BEV', 'hauling.ICE']
        producer_decision (Series): result of producer compliance search, *without* consumer response
        cross_subsidy_options_and_response (DataFrame): dataframe containing cross subsidy options and response
    它的核心任务是评估每一个价格方案的优劣程度**，并计算出两个关键的“误差”指标，这两个指标将共同决定哪个价格方案是当前迭代中的最佳选择。
    Returns:
        Nothing, updates ``cross_subsidy_options_and_response``

    """
    _cross_subsidy_options_and_response = dict()

    _cross_subsidy_options_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat] = 0
    _cross_subsidy_options_and_response['average_ALT_cross_subsidized_price_%s' % mcat] = 0
    _cross_subsidy_options_and_response['abs_share_delta_%s' % mcat] = 0

    if mcat == '':#这是一个特殊情况。当 mcat 为空字符串 '' 时，表示当前正在处理的是整个市场的顶层节点。在顶层，消费者总份额自然是100%，即1.0
        _cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mcat] = 1.0
        cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mcat] = 1.0

    for mc in cross_subsidy_group:
        _cross_subsidy_options_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat] += \
            producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mc] * \
            cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mc].values / \
            cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mcat].values#将子类别 (mc) 的成本，按其在父类别 (mcat) 中所占的相对份额进行加权，然后累加到父类别的总成本上

        _cross_subsidy_options_and_response['average_ALT_cross_subsidized_price_%s' % mcat] += \
            cross_subsidy_options_and_response['average_ALT_cross_subsidized_price_%s' % mc].values * \
            cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mc].values / \
            cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mcat].values#逻辑与计算成本完全相同，只是把 cost 换成了交叉补贴后的 price。最终目标就是让这个加权平均价格非常接近上面计算的加权平均成本

        _cross_subsidy_options_and_response['abs_share_delta_%s' % mc] = abs(
            producer_decision['producer_abs_share_frac_%s' % mc] -
            cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mc].values)#这是第一个核心指标的计算。它直接用生产商最初想卖的份额 (producer_abs_share_frac_...) 减去在当前价格下消费者实际愿买的份额 (consumer_abs_share_frac_...)，然后取绝对值

        _cross_subsidy_options_and_response['abs_share_delta_%s' % mcat] += \
            1 / len(cross_subsidy_group) * _cross_subsidy_options_and_response['abs_share_delta_%s' % mc]#将分组内所有子类别的份额误差求一个算术平均值，作为这个市场大类 (mcat) 的总体份额收敛误差

    _cross_subsidy_options_and_response['pricing_price_ratio_delta_%s' % mcat] = \
        abs(1 - _cross_subsidy_options_and_response['average_ALT_cross_subsidized_price_%s' % mcat] /
            _cross_subsidy_options_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat])#这是第二个核心指标。它用加权平均价格除以加权平均成本，得到一个比率。理想情况下这个比率应该是1；计算了这个比率与1之间的绝对差距。这个值越小，说明交叉补贴策略越接近“收入中性”

    # for development
    # _cross_subsidy_options_and_response['pricing_price_ratio_%s' % mcat] = \
    #     _cross_subsidy_options_and_response['average_ALT_cross_subsidized_price_%s' % mcat] / \
    #     _cross_subsidy_options_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat]

    _cross_subsidy_options_and_response['pricing_price_ratio_delta_%s_raw' % mcat] = \
        (1 - _cross_subsidy_options_and_response['average_ALT_cross_subsidized_price_%s' % mcat] /
            _cross_subsidy_options_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mcat])

    for k, v in _cross_subsidy_options_and_response.items():
        cross_subsidy_options_and_response[k] = v


def iterate_producer_cross_subsidy(calendar_year, compliance_id, best_producer_decision_and_response,
                                   candidate_mfr_composite_vehicles, iteration_log, producer_consumer_iteration_num,
                                   producer_market_classes, producer_decision, strategic_target_offset_Mg):
    """
    Perform producer pricing cross-subsidy iteration.  Cross-subsidy maintains the total average price, as well
    as average price by non-responsive market categories.  The goal is to achieve convergence between producer and
    consumer desired absolute market class shares, within a tolerance.  The cross-subsidy is implemented through
    price multipliers, the minimum and maximum range of which are user inputs (e.g. 0.95 -> 1.05).  The initial range
    of multipliers is the full span from min to max, subsequent iterations tighten the range and hone in on the
    multipliers that provide the most convergent result while maintaining the average prices mentioned above.
    通过调整不同车型的价格（即交叉补贴），来找到一个能让“生产者意愿”和“消费者选择”达成一致的均衡点
    Args:
        calendar_year (int): calendar year of the iteration
        compliance_id (str): manufacturer name, or 'consolidated_OEM'
        best_producer_decision_and_response (Series): producer compliance search result with
            consumer share response with best convergence
        candidate_mfr_composite_vehicles ([CompositeVehicles]): list of manufacturer composite vehicles, production
            candidates
        iteration_log (DataFrame): DataFrame of producer-consumer and cross-subsidy iteration data
        producer_consumer_iteration_num (int): producer-consumer iteration number
        producer_market_classes (list): list of candidate_mfr_composite_vehicles grouped by market class
        producer_decision (Series): result of producer compliance search, *without* consumer response
        strategic_target_offset_Mg (float): desired producer distance from compliance, in CO2e Mg, zero for compliance,
            > 0 for under-compliance, < 0 for over-compliance

    Returns:
        tuple of best producer decision and response, the iteration log, and last producer decision and response
        (best_producer_decision_and_response, iteration_log, cross_subsidy_options_and_response)

    """
    from producer import compliance_search

    producer_decision['context_new_vehicle_sales'] = producer_decision['total_sales']

    cross_subsidy_options_and_response = pd.DataFrame()

    market_class_tree = omega_globals.options.MarketClass.get_market_class_tree()
    # 2. 计算交叉补贴选项和消费者响应
    cross_subsidy_options_and_response, iteration_log = \
        calc_cross_subsidy_options_and_response(calendar_year, market_class_tree, compliance_id, producer_decision,
                                                cross_subsidy_options_and_response, producer_consumer_iteration_num,
                                                iteration_log, node_name='', verbose=False)

    max_error = 0
    cross_subsidy_options_and_response['max_share_delta_market_class'] = None
    for mcat in market_class_tree:
        if 'abs_share_delta_%s' % mcat in cross_subsidy_options_and_response:
            error = cross_subsidy_options_and_response['abs_share_delta_%s' % mcat] / \
                    cross_subsidy_options_and_response['consumer_abs_share_frac_%s' % mcat]
            if error > max_error:
                max_error = error
                cross_subsidy_options_and_response['max_share_delta_market_class'] = mcat

    # combine producer_decision with cross_subsidy_options_and_response to create producer_decision_and_response
    producer_decision_and_response = producer_decision.copy()
    for k in cross_subsidy_options_and_response.keys():
        producer_decision_and_response[k] = cross_subsidy_options_and_response[k]

    producer_decision_and_response['cross_subsidy_iteration_num'] = producer_consumer_iteration_num

    # temporarily assign shares to sales to calculate new consumer-share-weighted market_class values:
    for cv in candidate_mfr_composite_vehicles:
        cv.initial_registered_count = producer_decision_and_response[
                                          'consumer_abs_share_frac_' + cv.market_class_id + '.' + cv.alt_type] * \
                                      cv.market_class_share_frac

    calc_market_class_data_from_composite_vehicles(candidate_mfr_composite_vehicles, producer_decision_and_response)

    # updates producer_decision_and_response['new_vehicle_sales']:
    calc_sales_and_cost_data_from_consumer_abs_shares(calendar_year, compliance_id, producer_market_classes,
                                                      producer_decision_and_response)

    # distribute total sales to vehicle sales in producer decision and response
    compliance_search.create_production_options_from_shares(
        candidate_mfr_composite_vehicles, producer_decision_and_response,
        total_sales=producer_decision_and_response['new_vehicle_sales'])

    calc_market_data_from_sales(candidate_mfr_composite_vehicles, producer_decision_and_response)

    # the 0.01 factors in the below equation protect against divide by zero when/if standards are zero
    producer_decision_and_response['strategic_compliance_ratio'] = \
        (producer_decision_and_response['total_cert_co2e_megagrams'] - strategic_target_offset_Mg + 0.01) / \
        (producer_decision_and_response['total_target_co2e_megagrams'] + 0.01)

    compliant = producer_decision_and_response['strategic_compliance_ratio'] <= 1.0 or \
                abs(1 - producer_decision_and_response['strategic_compliance_ratio']) <= \
                omega_globals.options.producer_compliance_search_tolerance

    mcat_converged, share_convergence_error, cross_subsidy_pricing_error = \
        detect_producer_consumer_convergence(producer_decision_and_response, producer_market_classes)#比较生产者最初的份额 (producer_abs_share_frac_...) 和消费者最终的份额 (consumer_abs_share_frac_...) 之间的差异
    #返回一个布尔值 converged，判断差异是否在可接受的公差范围内
    if True or (best_producer_decision_and_response is None) or \
            (producer_decision_and_response['pricing_score']
             < best_producer_decision_and_response['pricing_score']):
        best_producer_decision_and_response = producer_decision_and_response.copy()

    logwrite_cross_subsidy_results(calendar_year, producer_market_classes, cross_subsidy_pricing_error,
                                   producer_consumer_iteration_num, producer_decision_and_response,
                                   share_convergence_error)

    update_cross_subsidy_log_data(producer_decision_and_response, calendar_year, compliance_id, mcat_converged,
                                  producer_consumer_iteration_num, compliant, share_convergence_error)

    if omega_globals.options.producer_shares_mode:
        # force consumer shares from producer shares, after having logged raw results above
        for mcat in [k for k in producer_decision_and_response.keys() if 'consumer_abs_' in k]:
            producer_decision_and_response[mcat] = producer_decision_and_response[mcat.replace('consumer', 'producer')]

    iteration_log.append(producer_decision_and_response)

    return best_producer_decision_and_response, iteration_log, producer_decision_and_response


def logwrite_cross_subsidy_results(calendar_year, producer_market_classes, cross_subsidy_pricing_error,
                                   producer_consumer_iteration_num, producer_decision_and_response,
                                   share_convergence_error):
    """
    Write cross-subsidy data to the console / session log

    Args:
        calendar_year (int): calendar year of the iteration
        producer_market_classes (list): list of producer market classes, e.g. ['hauling.ICE', 'hauling.BEV', ...]
        cross_subsidy_pricing_error (float): the cross subsidy pricing error
        producer_consumer_iteration_num (int): producer-consumer iteration number
        producer_decision_and_response (Series): producer decision and cross-subsidy iteration response data
        share_convergence_error (float): producer-consumer share convergence error

    Returns:
        Nothing, updates console log and ``omega_globals.price_modification_data``

    """
    if 'p-c_shares_and_costs' in omega_globals.options.verbose_console_modules:
        logwrite_shares_and_costs(calendar_year, producer_market_classes, share_convergence_error,
                                  cross_subsidy_pricing_error, producer_decision_and_response,
                                  producer_consumer_iteration_num, producer_consumer_iteration_num)

    multiplier_columns = ['cost_multiplier_%s' % mc for mc in sorted(producer_market_classes)]

    omega_globals.price_modification_data = dict()

    if 'cross_subsidy_multipliers' in omega_globals.options.verbose_console_modules:
        for mc, cc in zip(sorted(producer_market_classes), multiplier_columns):
            if cc in producer_decision_and_response:
                if mc in omega_globals.locked_price_modification_data:
                    omega_log.logwrite(('LOCKED %s' % cc).ljust(50) + '= %.5f' %
                                       omega_globals.locked_price_modification_data[mc]['market_class_multiplier'],
                                       echo_console=True)
                else:
                    omega_log.logwrite(('FINAL  %s' % cc).ljust(50) + '= %.5f' % producer_decision_and_response[cc],
                                       echo_console=True)

    if all(mc in producer_decision_and_response for mc in multiplier_columns):
        for mc, mc_mult in zip(sorted(producer_market_classes), producer_decision_and_response[multiplier_columns]):
            omega_globals.price_modification_data[mc] = dict()
            omega_globals.price_modification_data[mc]['market_class_multiplier'] = mc_mult
            omega_globals.price_modification_data[mc][
                'market_class_price_modification'] = PriceModifications.get_price_modification(calendar_year, mc)
    else:
        # no multipliers are generated when a market class tree has an only child (e.g. Tesla is BEV-only, no ICE)
        for mc in sorted(producer_market_classes):
            omega_globals.price_modification_data[mc] = dict()
            omega_globals.price_modification_data[mc]['market_class_multiplier'] = 1.0
            omega_globals.price_modification_data[mc][
                'market_class_price_modification'] = PriceModifications.get_price_modification(calendar_year, mc)


def search_cross_subsidies(calendar_year, compliance_id, mcat, cross_subsidy_group, producer_decision,
                           cross_subsidy_options_and_response, producer_consumer_iteration_num, iteration_log):
    """
    Search the available cross-subsidy space (as determined by min and max pricing multipliers) for multipliers that
    minimize the error between producer and consumer market shares while maintaining revenue neutrality for the
    producer.

    Args:
        calendar_year (int): the year in which the compliance calculations take place
        compliance_id (str): name of manufacturer, e.g. 'consolidated_OEM'
        mcat (str): market category, e.g. 'hauling' / 'non_hauling'
        cross_subsidy_group (list): list of cross-subsidized market classes, e.g. ['hauling.BEV', 'hauling.ICE']
        producer_decision (Series): result of producer compliance search, *without* consumer response
        cross_subsidy_options_and_response (DataFrame, Series): initially empty dataframe or Series containing cross
            subsidy options and response
        producer_consumer_iteration_num (int): producer-consumer iteration number
        iteration_log (DataFrame): DataFrame of producer-consumer iteration data

    Returns:
        tuple of ``cross_subsidy_options_and_response``, updated ``iteration_log``

    """
    multiplier_columns = ['cost_multiplier_%s' % mc for mc in cross_subsidy_group]

    mcat_cross_subsidy_iteration_num = 0
    prev_multiplier_range = dict()
    continue_search = True

    while continue_search:
        continue_search, cross_subsidy_options = \
            create_cross_subsidy_options(calendar_year, continue_search, cross_subsidy_group, multiplier_columns,
                                         prev_multiplier_range, producer_decision, cross_subsidy_options_and_response)

        cross_subsidy_options_and_response = \
            omega_globals.options.SalesShare.calc_shares(calendar_year, compliance_id, producer_decision,
                                                         cross_subsidy_options, mcat, cross_subsidy_group)

        calc_cross_subsidy_metrics(mcat, cross_subsidy_group, producer_decision, cross_subsidy_options_and_response)#返回各种评价指标
        #理想的解是两个误差都为0。我们可以把这两个误差想象成一个二维坐标系上的点 (份额误差, 定价误差)，我们的目标就是找到一个能让这个点最接近原点 (0, 0) 的价格乘数组合
        if mcat_cross_subsidy_iteration_num < 3:
            # take closest to origin to get in the ballpark
            cross_subsidy_options_and_response['pricing_score'] = \
                (cross_subsidy_options_and_response['pricing_price_ratio_delta_%s_raw' % mcat].values**2 +
                cross_subsidy_options_and_response['abs_share_delta_%s' % mcat].values**2)**0.5
        else:#欧氏距离中的平方项 (x²) 会对较大的误差给予不成比例的巨大惩罚。在微调阶段，我们不希望因为一个误差稍大一点点就被过度惩罚，从而错过最佳解。简单的线性求和 (x + y) 对所有误差的处理更加温和和线性，更适合在解的附近进行平滑的、精细的搜索。
            # take lowest error sum
            cross_subsidy_options_and_response['pricing_score'] = \
                cross_subsidy_options_and_response['pricing_price_ratio_delta_%s' % mcat].values + \
                cross_subsidy_options_and_response['abs_share_delta_%s' % mcat].values

        # select best score
        selected_cross_subsidy_index = cross_subsidy_options_and_response['pricing_score'].idxmin()

        # note selected option
        cross_subsidy_options_and_response['selected_cross_subsidy_option'] = 0
        cross_subsidy_options_and_response.loc[selected_cross_subsidy_index, 'selected_cross_subsidy_option'] = 1

        cross_subsidy_options_and_response['cross_subsidy_iteration_num_%s' % mcat] = \
            mcat_cross_subsidy_iteration_num

        if 'cross_subsidy_search' in omega_globals.options.verbose_log_modules:
            iteration_log.append(cross_subsidy_options_and_response)

        # select best cross subsidy option
        cross_subsidy_options_and_response = \
            cross_subsidy_options_and_response.loc[selected_cross_subsidy_index].copy()#只把得分最高的那一行（即最佳方案）筛选出来，并用它覆盖掉原来的 DataFrame

        share_convergence_error = cross_subsidy_options_and_response['abs_share_delta_%s' % mcat]
        cross_subsidy_pricing_error = cross_subsidy_options_and_response['pricing_price_ratio_delta_%s' % mcat]

        mcat_converged = (cross_subsidy_pricing_error <=
                          omega_globals.options.producer_cross_subsidy_price_tolerance) \
                         and \
                         (share_convergence_error <= omega_globals.options.producer_consumer_convergence_tolerance)#判断是否达到收敛标准

        mcat_cross_subsidy_iteration_num += 1

        # update iteration log
        update_cross_subsidy_log_data(cross_subsidy_options_and_response, calendar_year, compliance_id, mcat_converged,
                                      producer_consumer_iteration_num, None,
                                      cross_subsidy_options_and_response['abs_share_delta_%s' % mcat])

        iteration_log.append(cross_subsidy_options_and_response)

        continue_search = continue_search and not mcat_converged #如果之前的 create_cross_subsidy_options 函数发现搜索范围已经“坍塌”无法再缩小，它会把 continue_search 设为 False

    if cross_subsidy_options_and_response['consumer_constrained_%s' % mcat] and \
            'p-c_shares_and_costs' in omega_globals.options.verbose_console_modules:
        omega_log.logwrite('%%%%%% consumer %s shares constrained %%%%%%' % mcat)#如果最终选出的最佳方案，其消费者份额受到了外部约束（即达到了份额上限或下限），并且开启了详细日志，那么就在控制台打印一条警告信息。这有助于分析师了解收敛结果是否受到了人为约束的强烈影响

    update_cross_subsidy_group_console_log(cross_subsidy_group, share_convergence_error, cross_subsidy_pricing_error,
                                          mcat_converged)

    if 'cross_subsidy_search' in omega_globals.options.verbose_console_modules:
        omega_log.logwrite('')#将本轮搜索的最终结果（是否收敛、最终的份额误差和定价误差）以一种简洁的方式打印到控制台

    return cross_subsidy_options_and_response, iteration_log


def update_cross_subsidy_group_console_log(cross_subsidy_group, share_convergence_error, cross_subsidy_pricing_error,
                                          mcat_converged):
    """
    Write producer-consumer cross subsidy data to the console and log, if enabled by ``verbose_console_modules``.

    Args:
        cross_subsidy_group (list): e.g. ['hauling.ICE', 'hauling.BEV']
        share_convergence_error (float): producer-consumer convergence error
        cross_subsidy_pricing_error (float): cross-subsidy pricing error
        mcat_converged (bool): ``True`` if the market class price/cost ratioand the
            producer-consumer shares are within tolerance

    """

    if 'cross_subsidy_convergence' in omega_globals.options.verbose_console_modules:
        if mcat_converged:
            omega_log.logwrite('   PRODUCER-CONSUMER CONVERGED %s CE:%f, CSPE:%f' %
                               (' / '.join(cross_subsidy_group), share_convergence_error, cross_subsidy_pricing_error))
        else:
            omega_log.logwrite('** PRODUCER-CONSUMER CONVERGENCE FAIL %s CE:%f, CSPE:%f **' %
                               (' / '.join(cross_subsidy_group), share_convergence_error, cross_subsidy_pricing_error))


def calc_sales_and_cost_data_from_consumer_abs_shares(calendar_year, compliance_id, producer_market_classes,
                                                      producer_decision_and_response):
    """
    Calculate sales and cost/price data.  Namely, the absolute share delta between producer and consumer
    absolute market shares, the share weighted average cross subsidized price by market class, the total share weighted 
    average cross subsidized price, the average modified cross subsidized price by market class, the average new
    vehicle manufacturer cost and generalized cost, and total new vehicle sales, including the market response to
    average new vehicle manufacturer generalized cost.

    Args:
        calendar_year (int): calendar year of the iteration
        compliance_id (str): manufacturer name, or 'consolidated_OEM'
        producer_market_classes (list): list of producer market classes
        producer_decision_and_response (Series): producer compliance search result with consumer share response

    Returns:
        Updates ``producer_decision_and_response`` columns
        
    """
    producer_decision_and_response['average_ALT_cross_subsidized_price_total'] = 0
    producer_decision_and_response['average_ALT_modified_cross_subsidized_price_total'] = 0
    producer_decision_and_response['average_ALT_new_vehicle_mfr_cost'] = 0
    producer_decision_and_response['average_ALT_new_vehicle_mfr_generalized_cost'] = 0
    producer_decision_and_response['average_new_vehicle_mfr_generalized_cost'] = 0

    consumer_share_total = 0

    for mc in producer_market_classes:
        consumer_abs_share_frac = producer_decision_and_response['consumer_abs_share_frac_%s' % mc]
        consumer_share_total += consumer_abs_share_frac

        producer_decision_and_response['average_ALT_cross_subsidized_price_total'] += \
            producer_decision_and_response['average_ALT_cross_subsidized_price_%s' % mc] * \
            consumer_abs_share_frac

        producer_decision_and_response['average_ALT_modified_cross_subsidized_price_total'] += \
            producer_decision_and_response['average_ALT_modified_cross_subsidized_price_%s' % mc] * \
            consumer_abs_share_frac

        producer_decision_and_response['average_ALT_new_vehicle_mfr_cost'] += \
            producer_decision_and_response['average_ALT_new_vehicle_mfr_cost_%s' % mc] * \
            consumer_abs_share_frac

        producer_decision_and_response['average_ALT_new_vehicle_mfr_generalized_cost'] += \
            producer_decision_and_response['average_ALT_new_vehicle_mfr_generalized_cost_dollars_%s' % mc] * \
            consumer_abs_share_frac

        producer_decision_and_response['average_new_vehicle_mfr_generalized_cost'] += \
            producer_decision_and_response['average_new_vehicle_mfr_generalized_cost_dollars_%s' % mc] * \
            consumer_abs_share_frac

    # normalize values
    producer_decision_and_response['average_ALT_cross_subsidized_price_total'] /= consumer_share_total
    producer_decision_and_response['average_ALT_modified_cross_subsidized_price_total'] /= consumer_share_total
    producer_decision_and_response['average_ALT_new_vehicle_mfr_cost'] /= consumer_share_total
    producer_decision_and_response['average_ALT_new_vehicle_mfr_generalized_cost'] /= consumer_share_total
    producer_decision_and_response['average_new_vehicle_mfr_generalized_cost'] /= consumer_share_total

    producer_decision_and_response['new_vehicle_sales'] = \
        producer_decision_and_response['context_new_vehicle_sales'] * \
        sales_volume.new_vehicle_sales_response(calendar_year, compliance_id,
                                                producer_decision_and_response[
                                                    'average_new_vehicle_mfr_generalized_cost'])


def create_cross_subsidy_options(calendar_year, continue_search, mc_pair, multiplier_columns, prev_multiplier_range,
                                 producer_decision, producer_decision_and_response):
    """
    Calculate cross subsidy pricing options based on the allowable multiplier range, within a subsequently smaller
    range as iteration progresses, until the search collapses (min multiplier == max multiplier).

    Args:
        calendar_year (int): calendar year of the iteration
        continue_search (bool): prior value of ``continue_search``, set to ``False`` if search collapses
        mc_pair ([strs]):
        multiplier_columns ([strs]): list of cost multiplier columns,
            e.g. ['cost_multiplier_hauling.BEV', 'cost_multiplier_hauling.ICE', ...]
        prev_multiplier_range (dict): empty on first pass then contains a dict of previous multiplier ranges by market
            class, e.g. {'cost_multiplier_hauling.BEV': array([0.95, 0.98333333, 1.0, 1.01666667, 1.05]), ...}
        producer_decision (DataFrame): producer production decision dataframe
        producer_decision_and_response (DataFrame, Series): empty DataFrame on first pass then contains producer
            compliance search result and most-convergent consumer response to previous cross subsidy options as a
            Series

    Returns:
        tuple of whether to continue cross subsidy search, dataframe of producer decision with cross subsidy pricing
        options (continue_search, price_options_df)

    """
    first_pass = not all([mc in producer_decision_and_response for mc in multiplier_columns])#判断是否为第一次迭代。它检查 producer_decision_and_response 中是否已经包含了所有价格乘数列。如果没有，说明这是第一次进入 search_cross_subsidies 的循环，first_pass 为 True

    if first_pass and producer_decision_and_response.empty:
        price_options_df = pd.DataFrame()
    else:
        price_options_df = producer_decision_and_response.to_frame().transpose()
        # drop multiplier columns to prevent duplicates during cartesian product:把上一轮的乘数列从这个 DataFrame 中删除，为接下来生成新的、更精细的乘数网格做准备。
        price_options_df = price_options_df.drop(multiplier_columns, axis=1, errors='ignore')

    if first_pass:
        if omega_globals.options.producer_shares_mode:
            multiplier_range = np.array([1.0])#如果是特殊的 producer_shares_mode（生产者份额固定模式），则乘数固定为1.0，不做交叉补贴
        else:
            # first time through, span full range, including all 1's
            multiplier_range = \
                np.unique(np.append(np.linspace(omega_globals.options.consumer_pricing_multiplier_min,
                                                omega_globals.options.consumer_pricing_multiplier_max,
                                                omega_globals.options.consumer_pricing_num_options), 1.0))#生成一个覆盖全局设置中定义的最小到最大价格乘数范围的数组，确保 1.0（即不调价）这个选项一定被包含在内
    search_collapsed = True#在循环中，只要有一个类别的搜索范围没有收缩，它就会被置为 False
    for mc, mcc in zip(mc_pair, multiplier_columns):

        if not first_pass:
            # subsequent passes, tighten up search range to find convergent multipliers 总的来看：在每一轮价格谈判的最后，模型会选出 pricing_score 最低的那个方案，并以此为中心，在下一轮进行更小范围、更精确的搜索
            multiplier_range, search_collapsed = tighten_multiplier_range(mcc, prev_multiplier_range,
                                                                          producer_decision_and_response,
                                                                          search_collapsed)#这个函数会根据上一轮的最佳乘数，生成一个更小、更集中的新搜索范围，并判断搜索范围是否已经小到“坍塌”（即无法再缩小）
        else:
            if omega_globals.locked_price_modification_data and mc in omega_globals.locked_price_modification_data:
                # use recorded multipliers
                multiplier_range = \
                    np.array([omega_globals.locked_price_modification_data[mc]['market_class_multiplier']])#如果模型被配置为对某个市场类别使用一个“锁定”的、固定的价格乘数，那么 multiplier_range 就会被设置为仅包含这一个值的数组
            if 'cross_subsidy_search' in omega_globals.options.verbose_console_modules:
                omega_log.logwrite(('%s' % mcc).ljust(35) + '= MR:%s' % multiplier_range,
                                   echo_console=True)
        #price_options_df 会变成一个有多行一列的 DataFrame，列是 'cost_multiplier_hauling.BEV'，每一行是 multiplier_range 中的一个值
        price_options_df = cartesian_prod(price_options_df, pd.DataFrame(multiplier_range, columns=[mcc]))
        #计算交叉补贴后的价格。对于网格中的每一种组合（每一行），用该车型的基础制造成本乘以对应的价格乘数，得到交叉补贴后的新价格，并存入新的一列
        price_options_df['average_ALT_cross_subsidized_price_%s' % mc] = \
            producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mc] * price_options_df[mcc].values
        #获取该车型可能有的其他固定价格调整项（如补贴或税费），加到交叉补贴后的价格上，得到最终面向消费者的价格
        price_modification = PriceModifications.get_price_modification(calendar_year, mc)

        price_options_df['average_ALT_modified_cross_subsidized_price_%s' % mc] = \
            price_options_df['average_ALT_cross_subsidized_price_%s' % mc].values + price_modification

        prev_multiplier_range[mcc] = multiplier_range

    if not first_pass and search_collapsed:
        continue_search = False#这个判断在第一次迭代时不会触发。它的作用是在后续迭代中，如果发现所有类别的搜索范围都已经“坍塌”（即小到无法再缩小），就将 continue_search 设为 False，从而终止外层的 while 循环
        if 'cross_subsidy_search' in omega_globals.options.verbose_console_modules:
            omega_log.logwrite('SEARCH COLLAPSED')

    return continue_search, price_options_df


def tighten_multiplier_range(multiplier_column, prev_multiplier_ranges, producer_decision_and_response,
                             search_collapsed):
    """
    Tighten cross subsidy multiplier range.

    Args:
        multiplier_column (str): name of the multiplier range to tighten, e.g. 'cost_multiplier_hauling.BEV'
        prev_multiplier_ranges (dict): empty on first pass then contains a dict of previous multiplier ranges by market
            class, e.g. {'cost_multiplier_hauling.BEV': array([0.95, 0.98333333, 1.0, 1.01666667, 1.05]), ...}
        producer_decision_and_response (Series): contains producer compliance search result and most-convergent
            consumer response to previous cross subsidy options
        search_collapsed (bool): prior value of search collapsed, gets ANDed with collapse condition

    Returns:
        tuple of multiplier range array (e.g. array([1.01666667, 1.02777778, 1.03888889, 1.05])) and whether search has
        collapsed (multiplier_range, search_collapsed)

    """

    prev_multiplier = producer_decision_and_response[multiplier_column]
    prev_multiplier_range = prev_multiplier_ranges[multiplier_column]
    span_frac_gain = 6

    prev_multiplier_span_frac = \
        prev_multiplier_range[-1] / prev_multiplier_range[0] - 1

    index = np.nonzero(prev_multiplier_range == prev_multiplier)[0][0]

    if index == 0:#如果上一轮的最佳值恰好是范围的最小值 (index == 0) 或最大值 (index == len(...) - 1)，这暗示着真正的最优解可能还在这个范围的外面；此时，代码会尝试向外扩展搜索边界。它用上一轮的范围跨度 prev_multiplier_span_frac 乘以一个增益系数 span_frac_gain，来计算一个新的、更宽的边界
        min_val = max(omega_globals.options.consumer_pricing_multiplier_min,
                      prev_multiplier * (1 - prev_multiplier_span_frac * span_frac_gain))

        if prev_multiplier > omega_globals.options.consumer_pricing_multiplier_min and \
                'cross_subsidy_search' in omega_globals.options.verbose_console_modules:
            print('++ hit minimum %s %f : %f' % (multiplier_column, prev_multiplier, min_val))
    else:
        min_val = prev_multiplier_range[index - 1]

    if index == len(prev_multiplier_range) - 1:
        max_val = min(omega_globals.options.consumer_pricing_multiplier_max,
                      prev_multiplier * (1 + prev_multiplier_span_frac * span_frac_gain))

        if prev_multiplier > omega_globals.options.consumer_pricing_multiplier_max and \
                'cross_subsidy_search' in omega_globals.options.verbose_console_modules:
            print('++ hit maximum %s %f : %f' % (multiplier_column, prev_multiplier, max_val))
    else:
        max_val = prev_multiplier_range[index + 1]

    # try new range, include prior value in range...
    multiplier_range = np.unique(np.append(
        np.linspace(min_val, max_val, omega_globals.options.consumer_pricing_num_options),
        prev_multiplier))

    # CU RV 如果新生成的范围 multiplier_range 的长度只有2（意味着 min_val 和 max_val 几乎相等），或者 max_val 和 min_val 的差值已经小到一个极小值（如 1e-4），那么就认为当前这个维度的搜索已经“坍塌”，无法再缩小了
    search_collapsed = search_collapsed and ((len(multiplier_range) == 2) or (max_val - min_val <= 1e-4))#只有当所有参与交叉补贴的车型维度都坍塌时，最终的 search_collapsed 才会为 True
    if 'cross_subsidy_search' in omega_globals.options.verbose_console_modules:
        mr_str = str(['%.8f' % m for m in multiplier_range]).replace("'", '')
        omega_log.logwrite(('%s' % multiplier_column).ljust(35) + '= %.5f MR:%s R:%f' % (
            prev_multiplier, mr_str, max_val - min_val))

    return multiplier_range, search_collapsed


def calc_market_class_data_from_composite_vehicles(candidate_mfr_composite_vehicles, producer_decision):
    """
    Creates a dictionary of candidate vehicles binned by market class, calculates market class and market category
    data via ``calc_market_class_data()`` and ``calc_market_category_data()``

    Args:
        candidate_mfr_composite_vehicles (list): list of candidate composite vehicles that minimize producer compliance
            cost
        producer_decision (Series): Series that corresponds with candidate_mfr_composite_vehicles, has producer market
            shares, costs, compliance data (Mg CO2e), may also contain consumer response

    Returns:
        list of producer market classes (market classes with candidate vehicles),
        updates producer_decision with calculated market data

    See Also:
        ``calc_market_class_data()``, ``calc_market_category_data()``

    """
    # group vehicles by market class
    market_class_vehicle_dict = omega_globals.options.MarketClass.get_market_class_dict()
    for new_veh in candidate_mfr_composite_vehicles:
        market_class_vehicle_dict[new_veh.market_class_id].append(new_veh)

    calc_market_class_data_from_market_class_vehicles(market_class_vehicle_dict, producer_decision)

    return [k for k in market_class_vehicle_dict.keys() if market_class_vehicle_dict[k]]


def calc_market_class_data_from_market_class_vehicles(market_class_vehicle_dict, producer_decision):
    """
    Calculate market class average CO2e g/mi, kWh/mi, manufacturer new vehicle cost and generalized cost, average fuel
    price, and other sales-weighted vehicle attributes such as footprint, curbweight, etc.

    Args:
        market_class_vehicle_dict (dict): candidate vehicles binned by market class
        producer_decision (Series): Series that corresponds with candidate_mfr_composite_vehicles, has producer market
            shares, costs, compliance data (Mg CO2e), may also contain consumer response

    Returns:
        Nothing, updates ``producer_decsion`` with calculated market data

    """
    # calculate sales-weighted values by market class
    weight_by = 'market_class_share_frac'

    for mc in omega_globals.options.MarketClass.market_classes:
        market_class_vehicles = market_class_vehicle_dict[mc]

        # calculate market class values based on all vehicles, ALT and no-ALT:
        if market_class_vehicles:
            producer_decision['average_onroad_direct_co2e_gpmi_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'onroad_direct_co2e_grams_per_mile')

            producer_decision['average_onroad_direct_kwh_pmi_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'onroad_direct_kwh_per_mile')

            producer_decision['average_new_vehicle_mfr_cost_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'new_vehicle_mfr_cost_dollars')

            producer_decision['average_new_vehicle_mfr_generalized_cost_dollars_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by,
                               'new_vehicle_mfr_generalized_cost_dollars')

            producer_decision['average_retail_fuel_price_dollars_per_unit_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'retail_fuel_price_dollars_per_unit')

            producer_decision['average_curbweight_lbs_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'curbweight_lbs')

            producer_decision['average_rated_hp_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'rated_hp')

            producer_decision['average_footprint_ft2_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'footprint_ft2')
            #计算燃料相关效率
            if 'ICE' in mc:
                producer_decision['average_onroad_mpg_%s' % mc] = \
                    OnroadFuel.grams_co2e_per_gallon / \
                    max(sys.float_info.epsilon, producer_decision['average_onroad_direct_co2e_gpmi_%s' % mc])
            else:
                producer_decision['average_onroad_mpg_%s' % mc] = \
                    OnroadFuel.kilowatt_hours_per_gallon / \
                    max(sys.float_info.epsilon, producer_decision['average_onroad_direct_kwh_pmi_%s' % mc])

        else:
            producer_decision['average_onroad_direct_co2e_gpmi_%s' % mc] = 0
            producer_decision['average_onroad_direct_kwh_pmi_%s' % mc] = 0
            producer_decision['average_new_vehicle_mfr_cost_%s' % mc] = 0
            producer_decision['average_new_vehicle_mfr_generalized_cost_dollars_%s' % mc] = 0
            producer_decision['average_retail_fuel_price_dollars_per_unit_%s' % mc] = 0
            producer_decision['average_curbweight_lbs_%s' % mc] = 0
            producer_decision['average_rated_hp_%s' % mc] = 0
            producer_decision['average_footprint_ft2_%s' % mc] = 0
            producer_decision['average_onroad_mpg_%s' % mc] = 0

        # calculate ALT-only values needed by the consumer module:
        # costs and other values the consumer is basing ICE/BEV decisions on should only be made based on the ALT消费者基于ICE/BEV决策的成本和其他值应仅基于ALT
        # vehicles which are comparable to each other, unless there aren't any, then use the NO_ALTs车辆应彼此具有可比性，除非没有可比车辆，则使用NO_ALTs
        if [mcv for mcv in market_class_vehicles if mcv.alt_type == 'ALT']:#它把所有 NO_ALT 的利基车型或占位车型全部排除掉，确保后续计算只基于主流竞争车型
            market_class_vehicles = [mcv for mcv in market_class_vehicles if mcv.alt_type == 'ALT']

        if market_class_vehicles:
            producer_decision['average_ALT_onroad_direct_co2e_gpmi_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'onroad_direct_co2e_grams_per_mile')

            producer_decision['average_ALT_onroad_direct_kwh_pmi_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'onroad_direct_kwh_per_mile')

            producer_decision['average_ALT_retail_fuel_price_dollars_per_unit_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'retail_fuel_price_dollars_per_unit')

            producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by, 'new_vehicle_mfr_cost_dollars')

            producer_decision['average_ALT_new_vehicle_mfr_generalized_cost_dollars_%s' % mc] = \
                weighted_value(market_class_vehicles, weight_by,
                               'new_vehicle_mfr_generalized_cost_dollars')
        else:
            producer_decision['average_ALT_onroad_direct_co2e_gpmi_%s' % mc] = 0
            producer_decision['average_ALT_onroad_direct_kwh_pmi_%s' % mc] = 0
            producer_decision['average_ALT_retail_fuel_price_dollars_per_unit_%s' % mc] = 0
            producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mc] = 0
            producer_decision['average_ALT_new_vehicle_mfr_generalized_cost_dollars_%s' % mc] = 0


def calc_market_data_from_sales(candidate_mfr_composite_vehicles, producer_decision):
    """
    Calculates market class and market category data via ``calc_market_class_sales_from_producer_decision()`` and
    ``calc_market_category_data_from_sales()``

    Args:
        candidate_mfr_composite_vehicles (list): list of candidate composite vehicles that minimize producer compliance
            cost
        producer_decision (Series): Series that corresponds with candidate_mfr_composite_vehicles, has producer market
            shares, costs, compliance data (Mg CO2e), may also contain consumer response

    Returns:
        updates producer_decision with calculated market data

    See Also:
        ``calc_market_class_data()``, ``calc_market_category_data()``

    """
    # group vehicles by market class
    market_class_vehicle_dict = omega_globals.options.MarketClass.get_market_class_dict()
    for new_veh in candidate_mfr_composite_vehicles:
        market_class_vehicle_dict[new_veh.market_class_id].append(new_veh)

    calc_market_class_sales_from_producer_decision(market_class_vehicle_dict, producer_decision)

    calc_market_category_data_from_sales(producer_decision)


def calc_market_class_sales_from_producer_decision(market_class_vehicle_dict, producer_decision):
    """
    Calculate market class sales from ``producer_decision`` composite vehicle sales.

    Args:
        market_class_vehicle_dict (dict): candidate vehicles binned by market class
        producer_decision (Series): Series that corresponds with candidate_mfr_composite_vehicles, has producer market
            shares, costs, compliance data (Mg CO2e), may also contain consumer response

    Returns:
        Nothing, updates market class values in ``producer_decision``

    """
    calc_producer_abs_share_frac_from_sales = dict()
    for mc in omega_globals.options.MarketClass.market_classes:
        market_class_vehicles = market_class_vehicle_dict[mc]
        calc_producer_abs_share_frac_from_sales[mc] = False
        if market_class_vehicles and 'producer_abs_share_frac_%s' % mc not in producer_decision:
            # after create_share_sweeps() we need to calculate this, but we don't want to re-calculate it after the这个计算只在生产者搜索之后、消费者响应之前进行一次
            # consumer response or it will short-circuit the producer-consumer iteration, since the consumer response如果在消费者响应后重新计算，会用消费者的新销量覆盖生产者的原始意图，导致迭代无法收敛。
            # distributes new sales and the new sales will calculate exactly to the consumer market shares...我们会用消费者的销量，计算出一个新的“生产者份额”，这个份额会完美地等于消费者份额，短路了
            producer_decision['producer_abs_share_frac_%s' % mc] = 0
            calc_producer_abs_share_frac_from_sales[mc] = True

    # absolute shares and sales are based on all vehicles, whether ALT or not绝对份额和销量是基于所有车辆的（包括ALT和NO_ALT）
    for mc in omega_globals.options.MarketClass.market_classes:
        market_class_vehicles = market_class_vehicle_dict[mc]
        if market_class_vehicles:
            producer_decision['sales_%s' % mc] = 0
            for v in market_class_vehicles:
                producer_decision['sales_%s' % mc] += producer_decision['veh_%s_sales' % v.vehicle_id]

            if calc_producer_abs_share_frac_from_sales[mc]:#如果之前设置了标志，则计算生产者的绝对市场份额
                producer_decision['producer_abs_share_frac_%s' % mc] += \
                    producer_decision['sales_%s' % mc] / producer_decision['total_sales']
        else:
            producer_decision['sales_%s' % mc] = 0
            producer_decision['producer_abs_share_frac_%s' % mc] = 0


def calc_market_category_data_from_sales(producer_decision):
    """
    Calculate market category average cost and generalized cost, average cross subsidized price, sales, producer
    absolute shares and other sales-weighted market class attributes such as footprint, curbweight, etc.

    Args:
        producer_decision (Series): Series that corresponds with candidate_mfr_composite_vehicles, has producer market
            shares, costs, compliance data (Mg CO2e), may also contain consumer response

    Returns:
        Nothing, updates ``producer_decsion`` with calculated market category data

    """
    for mcat in omega_globals.options.MarketClass.market_categories: # 初始化该市场大类的各项属性
        producer_decision['average_onroad_direct_co2e_gpmi_%s' % mcat] = 0
        producer_decision['average_onroad_direct_kwh_pmi_%s' % mcat] = 0
        producer_decision['average_new_vehicle_mfr_cost_%s' % mcat] = 0
        producer_decision['average_new_vehicle_mfr_generalized_cost_dollars_%s' % mcat] = 0
        producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mcat] = 0
        producer_decision['average_ALT_cross_subsidized_price_%s' % mcat] = 0
        producer_decision['average_curbweight_lbs_%s' % mcat] = 0
        producer_decision['average_rated_hp_%s' % mcat] = 0
        producer_decision['average_footprint_ft2_%s' % mcat] = 0
        producer_decision['average_onroad_mpg_%s' % mcat] = 0
        producer_decision['sales_%s' % mcat] = 0
        producer_decision['producer_abs_share_frac_%s' % mcat] = 0

        for mc in omega_globals.options.MarketClass.market_classes:
            mc_sales = np.maximum(1, producer_decision['sales_%s' % mc])

            if mcat in mc.split('.'):
                producer_decision['average_onroad_direct_co2e_gpmi_%s' % mcat] += \
                    producer_decision['average_onroad_direct_co2e_gpmi_%s' % mc] * mc_sales# 将市场类别的属性值，乘以该类别的销量，累加到市场大类上

                producer_decision['average_onroad_direct_kwh_pmi_%s' % mcat] += \
                    producer_decision['average_onroad_direct_kwh_pmi_%s' % mc] * mc_sales

                producer_decision['average_new_vehicle_mfr_cost_%s' % mcat] += \
                    producer_decision['average_new_vehicle_mfr_cost_%s' % mc] * mc_sales

                producer_decision['average_new_vehicle_mfr_generalized_cost_dollars_%s' % mcat] += \
                    producer_decision['average_new_vehicle_mfr_generalized_cost_dollars_%s' % mc] * mc_sales

                if 'average_ALT_new_vehicle_mfr_cost_%s' % mc in producer_decision:
                    producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mcat] += \
                        producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mc] * mc_sales

                if 'average_ALT_cross_subsidized_price_%s' % mc in producer_decision:
                    producer_decision['average_ALT_cross_subsidized_price_%s' % mcat] += \
                        producer_decision['average_ALT_cross_subsidized_price_%s' % mc] * mc_sales

                producer_decision['average_curbweight_lbs_%s' % mcat] += \
                    producer_decision['average_curbweight_lbs_%s' % mc] * mc_sales

                producer_decision['average_rated_hp_%s' % mcat] += \
                    producer_decision['average_rated_hp_%s' % mc] * mc_sales

                producer_decision['average_footprint_ft2_%s' % mcat] += \
                    producer_decision['average_footprint_ft2_%s' % mc] * mc_sales

                producer_decision['average_onroad_mpg_%s' % mcat] += \
                    producer_decision['average_onroad_mpg_%s' % mc] * mc_sales

                producer_decision['sales_%s' % mcat] += \
                    producer_decision['sales_%s' % mc]

                if 'producer_abs_share_frac_%s' % mc in producer_decision:
                    producer_decision['producer_abs_share_frac_%s' % mcat] += \
                        producer_decision['producer_abs_share_frac_%s' % mc]

        mcat_sales = np.maximum(1, producer_decision['sales_%s' % mcat])

        producer_decision['average_onroad_direct_co2e_gpmi_%s' % mcat] /= mcat_sales

        producer_decision['average_onroad_direct_kwh_pmi_%s' % mcat] /= mcat_sales

        producer_decision['average_new_vehicle_mfr_cost_%s' % mcat] /= mcat_sales

        producer_decision['average_new_vehicle_mfr_generalized_cost_dollars_%s' % mcat] /= mcat_sales

        producer_decision['average_ALT_new_vehicle_mfr_cost_%s' % mcat] /= mcat_sales

        producer_decision['average_ALT_cross_subsidized_price_%s' % mcat] /= mcat_sales

        producer_decision['average_curbweight_lbs_%s' % mcat] /= mcat_sales

        producer_decision['average_rated_hp_%s' % mcat] /= mcat_sales

        producer_decision['average_footprint_ft2_%s' % mcat] /= mcat_sales

        producer_decision['average_onroad_mpg_%s' % mcat] /= mcat_sales


def detect_producer_consumer_convergence(producer_decision_and_response, producer_market_classes):
    """
    Detect producer-consumer market share convergence.

    Args:
        producer_decision_and_response (Series): contains producer compliance search result and most-convergent
            consumer response to previous cross subsidy options
        producer_market_classes (list): list of producer market classes

    Returns:
        tuple of convergence bool and share convergence error and cross subsidy pricing error

    """
    producer_decision_and_response['price_cost_ratio_total'] = \
        (producer_decision_and_response['average_ALT_cross_subsidized_price_total'] /
         producer_decision_and_response['average_ALT_new_vehicle_mfr_cost'])

    cross_subsidy_pricing_error = abs(1 - producer_decision_and_response['price_cost_ratio_total'])
    converged = cross_subsidy_pricing_error <= omega_globals.options.producer_cross_subsidy_price_tolerance or \
                omega_globals.options.producer_shares_mode

    share_convergence_error = 0
    for mc in producer_market_classes:
        if 'consumer_abs_share_frac_%s' % mc in producer_decision_and_response:
            share_convergence_error = \
                max(share_convergence_error, abs(producer_decision_and_response['producer_abs_share_frac_%s' % mc] -
                                                 producer_decision_and_response['consumer_abs_share_frac_%s' % mc]))
            converged = converged and (
                        share_convergence_error <= omega_globals.options.producer_consumer_convergence_tolerance)

    return converged, share_convergence_error, cross_subsidy_pricing_error


def get_module(module_name):
    """
    Get a Python module by module name

    Args:
        module_name (str): e.g. 'consumer.market_classes'

    Returns:
        The module specified by the module name

    """
    import importlib
    import importlib.util

    if module_name in sys.modules:
        module = sys.modules[module_name]
    else:
        module_relpath = str.rsplit(module_name, '.', maxsplit=1)[0].replace('.', os.sep)
        module_suffix = str.split(module_name, '.')[1]
        module_path = \
            omega_globals.options.omega_model_path + os.sep + module_relpath + os.sep + '%s.py' % module_suffix

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    return module


def import_user_definable_submodules():
    """
    Import dynamic modules that are specified by the input file input template name and set the session runtime
    options appropriately.

    Returns:
        List of template/input errors, else empty list on success

    """
    init_fail = []

    # user-definable context modules
    module_name = get_template_name(omega_globals.options.ice_vehicle_simulation_results_file)
    omega_globals.options.CostCloud = get_module(module_name).CostCloud

    module_name = get_template_name(omega_globals.options.powertrain_cost_input_file)
    omega_globals.options.PowertrainCost = get_module(module_name).PowertrainCost

    module_name = get_template_name(omega_globals.options.context_electricity_prices_file)
    omega_globals.options.ElectricityPrices = get_module(module_name).ElectricityPrices

    # user-definable policy modules
    module_name = get_template_name(omega_globals.options.policy_reg_classes_file)
    omega_globals.options.RegulatoryClasses = get_module(module_name).RegulatoryClasses

    init_fail += omega_globals.options.RegulatoryClasses.init_from_file(
        omega_globals.options.policy_reg_classes_file)

    module_name = get_template_name(omega_globals.options.policy_targets_file)
    omega_globals.options.VehicleTargets = get_module(module_name).VehicleTargets

    module_name = get_template_name(omega_globals.options.nev_requirements_file)
    if module_name:
        omega_globals.options.NEVRequirements = get_module(module_name).NEVRequirements

    module_name = get_template_name(omega_globals.options.offcycle_credits_file)
    omega_globals.options.OffCycleCredits = get_module(module_name).OffCycleCredits

    # user-definable consumer modules
    module_name = get_template_name(omega_globals.options.vehicle_reregistration_file)
    omega_globals.options.Reregistration = get_module(module_name).Reregistration

    module_name = get_template_name(omega_globals.options.onroad_vmt_file)
    omega_globals.options.OnroadVMT = get_module(module_name).OnroadVMT

    module_name = get_template_name(omega_globals.options.sales_share_file)
    omega_globals.options.SalesShare = get_module(module_name).SalesShare

    module_name = get_template_name(omega_globals.options.market_classes_file)
    omega_globals.options.MarketClass = get_module(module_name).MarketClass

    # user-definable producer modules
    module_name = get_template_name(omega_globals.options.producer_generalized_cost_file)
    omega_globals.options.ProducerGeneralizedCost = get_module(module_name).ProducerGeneralizedCost

    return init_fail


def init_user_definable_decomposition_attributes(verbose_init):
    """
    Init user definable decomposition attributes.  Decomposition attributes are values that are tracked at each point
    in a vehicle's cost curve / frontier during composition and are interpolated during decomposition.  Examples
    of decomposition attributes are individual drive cycle results and off-cycle credit values.  Technology application
    can also be tracked via optional flags in the simulated vehicles (cost cloud) data.

    Args:
        verbose_init (bool): if ``True`` enable additional init output to console

    Returns:
        List of template/input errors, else empty list on success

    See Also:
        ``producer.vehicles.DecompositionAttributes``, ``producer.vehicles.Vehicle``

    """
    from policy.drive_cycles import DriveCycles
    from producer.vehicles import Vehicle, DecompositionAttributes

    init_fail = []

    # init drive cycles PRIOR to CostCloud since CostCloud needs the drive cycle names for validation
    init_fail += DriveCycles.init_from_file(omega_globals.options.drive_cycles_file,
                                            verbose=verbose_init)

    init_fail += omega_globals.options.CostCloud. \
        init_cost_clouds_from_files(omega_globals.options.ice_vehicle_simulation_results_file,
                                    omega_globals.options.bev_vehicle_simulation_results_file,
                                    omega_globals.options.phev_vehicle_simulation_results_file,
                                    verbose=verbose_init)

    init_fail += omega_globals.options.OffCycleCredits.init_from_file(omega_globals.options.offcycle_credits_file,
                                                                      verbose=verbose_init)

    vehicle_columns = get_template_columns(omega_globals.options.vehicles_file)
    Vehicle.dynamic_columns = list(
        set.difference(set(vehicle_columns), Vehicle.mandatory_input_template_columns))
    for dc in Vehicle.dynamic_columns:
        Vehicle.dynamic_attributes.append(make_valid_python_identifier(dc))

    DecompositionAttributes.init()

    return init_fail


def init_omega(session_runtime_options):
    """
    Initialize OMEGA data structures.

    Args:
        session_runtime_options (OMEGASessionSettings): session runtime options

    Returns:
        List of template/input errors, else empty list on success

    """
    # set up global variables:
    omega_globals.options = session_runtime_options

    if omega_globals.options.auto_close_figures:
        import matplotlib
        matplotlib.use('Agg')

    omega_log.init_logfile()

    omega_log.logwrite("Initializing %s:" % omega_globals.options.session_unique_name)

    init_fail = []

    init_fail += import_user_definable_submodules()

    from context.onroad_fuels import OnroadFuel
    from context.fuel_prices import FuelPrice
    from context.new_vehicle_market import NewVehicleMarket
    from context.price_modifications import PriceModifications  # needs market classes
    from context.production_constraints import ProductionConstraints
    from context.mass_scaling import MassScaling
    from context.body_styles import BodyStyles
    from context.glider_cost import GliderCost

    from policy.upstream_methods import UpstreamMethods
    from policy.utility_factors import UtilityFactorMethods
    from policy.required_sales_share import RequiredSalesShare
    from policy.drive_cycles import DriveCycles
    from policy.drive_cycle_weights import DriveCycleWeights
    from policy.drive_cycle_ballast import DriveCycleBallast
    from policy.incentives import Incentives
    from policy.policy_fuels import PolicyFuel
    from policy.credit_banking import CreditBank
    from policy.workfactor_definition import WorkFactor

    from producer.manufacturers import Manufacturer
    from producer.manufacturer_annual_data import ManufacturerAnnualData
    from producer.vehicle_aggregation import VehicleAggregation
    from producer.vehicles import Vehicle, DecompositionAttributes
    from producer.vehicle_annual_data import VehicleAnnualData
    from producer import compliance_search

    from context.ip_deflators import ImplicitPriceDeflators

    from consumer.sales_volume import init_sales_volume

    file_io.validate_folder(omega_globals.options.output_folder)

    verbose_init = omega_globals.options.verbose

    try:
        init_fail = init_user_definable_decomposition_attributes(verbose_init)

        # load remaining input data

        init_sales_volume()

        init_fail += omega_globals.options.MarketClass.init_from_file(omega_globals.options.market_classes_file,
                                                                      verbose=verbose_init)

        init_fail += omega_globals.options.SalesShare.init_from_file(omega_globals.options.sales_share_file,
                                                                     verbose=verbose_init)

        init_fail += omega_globals.options.Reregistration.init_from_file(
            omega_globals.options.vehicle_reregistration_file,
            verbose=verbose_init)

        init_fail += omega_globals.options.OnroadVMT.init_from_file(omega_globals.options.onroad_vmt_file,
                                                                    verbose=verbose_init)

        init_fail += OnroadFuel.init_from_file(omega_globals.options.onroad_fuels_file,
                                               verbose=verbose_init)

        init_fail += NewVehicleMarket.init_from_file(omega_globals.options.context_new_vehicle_market_file,
                                                     verbose=verbose_init)

        # must come after NewVehicleMarket and OnroadFuel init for input validation
        init_fail += FuelPrice.init_from_file(omega_globals.options.context_fuel_prices_file,
                                              verbose=verbose_init)

        init_fail += omega_globals.options.ElectricityPrices.init_from_file(
            omega_globals.options.context_electricity_prices_file, verbose=verbose_init
        )

        init_fail += BodyStyles.init_from_file(omega_globals.options.body_styles_file,
                                               verbose=verbose_init)

        NewVehicleMarket.init_context_new_vehicle_generalized_costs(
            omega_globals.options.context_new_vehicle_generalized_costs_file)

        init_fail += PriceModifications.init_from_file(omega_globals.options.vehicle_price_modifications_file,
                                                       verbose=verbose_init)

        init_fail += omega_globals.options.ProducerGeneralizedCost.init_from_file(
            omega_globals.options.producer_generalized_cost_file, verbose=verbose_init)

        init_fail += ProductionConstraints.init_from_file(omega_globals.options.production_constraints_file,
                                                          verbose=verbose_init)

        init_fail += MassScaling.init_from_file(omega_globals.options.mass_scaling_file,
                                                verbose=verbose_init)

        init_fail += UpstreamMethods.init_from_file(omega_globals.options.fuel_upstream_methods_file,
                                                    verbose=verbose_init)

        init_fail += UtilityFactorMethods.init_from_file(omega_globals.options.utility_factor_methods_file,
                                                    verbose=verbose_init)

        init_fail += RequiredSalesShare.init_from_file(omega_globals.options.required_sales_share_file,
                                                       verbose=verbose_init)

        init_fail += DriveCycleWeights.init_from_file(omega_globals.options.drive_cycle_weights_file,
                                                      verbose=verbose_init)

        init_fail += DriveCycleBallast.init_from_file(omega_globals.options.drive_cycle_ballast_file,
                                                      verbose=verbose_init)

        init_fail += Incentives.init_from_file(omega_globals.options.production_multipliers_file,
                                               verbose=verbose_init)

        init_fail += omega_globals.options.VehicleTargets.init_from_file(omega_globals.options.policy_targets_file,
                                                                         verbose=verbose_init)

        if omega_globals.options.NEVRequirements:
            init_fail += omega_globals.options.NEVRequirements.init_from_file(
                omega_globals.options.nev_requirements_file,
                                                                         verbose=verbose_init)

        init_fail += PolicyFuel.init_from_file(omega_globals.options.policy_fuels_file,
                                               verbose=verbose_init)

        init_fail += CreditBank.validate_ghg_credit_params_template(omega_globals.options.ghg_credit_params_file,
                                                                    verbose=verbose_init)

        init_fail += Manufacturer.init_from_file(omega_globals.options.manufacturers_file,
                                                          verbose=verbose_init)

        init_fail += WorkFactor.init_from_file(omega_globals.options.workfactor_definition_file, verbose=verbose_init)

        # must be after Manufacturer init for input validation
        init_fail += CreditBank.validate_ghg_credits_template(omega_globals.options.ghg_credits_file,
                                                              verbose=verbose_init)

        init_fail += ImplicitPriceDeflators.init_from_file(omega_globals.options.ip_deflators_file,
                                                           verbose=verbose_init)

        init_fail += omega_globals.options.PowertrainCost.init_from_file(omega_globals.options.powertrain_cost_input_file,
                                                   verbose=verbose_init)

        init_fail += GliderCost.init_from_file(omega_globals.options.glider_cost_input_file,
                                               verbose=verbose_init)

        init_fail += VehicleAnnualData.init_vehicle_annual_data()

        init_fail += ManufacturerAnnualData.init_manufacturer_annual_data()

        if not init_fail:
            init_fail += VehicleAggregation.init_from_file(omega_globals.options.vehicles_file,
                                                           verbose=verbose_init)

            init_fail += Vehicle.init_from_file(omega_globals.options.onroad_vehicle_calculations_file,
                                                     verbose=verbose_init)

        if not init_fail:
            # initial year = initial fleet model year (latest year of data)这段代码会根据基准年车辆文件中的数据自动重新计算分析初始年
            #获取基准年车辆文件(vehicles_ldv_MY2022_20231211.csv)中所有车辆的模型年，找出其中最小值（这通常是基准年），将分析初始年设置为该值加1
            omega_globals.options.analysis_initial_year = \
                min([v.model_year for v in omega_globals.finalized_vehicles]) + 1

            # update vehicle annual data for base year fleet
            stock.update_stock(omega_globals.options.analysis_initial_year - 1)

    except:
        init_fail += ["\n#INIT FAIL\n%s\n" % traceback.format_exc()]

    return init_fail


def poolstart():
    """
    Placeholder for pool startup function

    Returns:
        ``None``

    """
    return None
    # CU


def error_callback(e):
    """
    Print multiprocess error callback to the console.

    Args:
        e (BaseException): exception info

    """
    print('error_callback_%s' % __name__)
    print(e)


def run_omega(session_runtime_options, standalone_run=False):
    """
    Run a single OMEGA simulation session and run session postproc.

    Args:
        session_runtime_options (OMEGASessionSettings): session runtime options
        standalone_run (bool): True if session is run outside of the batch process

    """
    import traceback
    import time
    import copy

    session_runtime_options.start_time = time.time()
    session_runtime_options.standalone_run = standalone_run
    # session_runtime_options.multiprocessing = session_runtime_options.multiprocessing

    if 0.0 < session_runtime_options.credit_market_efficiency < 1.0 or session_runtime_options.force_two_pass:
        # imperfect trading or force two-pass
        consolidate = [True, False]
    elif session_runtime_options.credit_market_efficiency == 1.0:
        # perfect trading
        consolidate = [True]
    else:
        # no trading
        consolidate = [False]

    output_folders = []

    if session_runtime_options.notification_destination and session_runtime_options.notification_email \
            and session_runtime_options.notification_password:
        send_text(session_runtime_options.notification_destination,
                  'Starting %s...' % session_runtime_options.session_unique_name,
                  session_runtime_options.notification_email, session_runtime_options.notification_password)

    try:

        manufacturer_annual_data_table = None
        manufacturer_gigawatthour_limit_data = None
        omega_globals.cumulative_battery_GWh = {'total': 0}

        for omega_globals.pass_num in range(len(consolidate)):

            omega_globals.finalized_vehicles = []

            session_runtime_options.consolidate_manufacturers = consolidate[omega_globals.pass_num]

            if session_runtime_options.use_prerun_context_outputs:
                session_runtime_options.context_new_vehicle_generalized_costs_file = \
                    '%s%scontext_new_vehicle_prices_%d.csv' % \
                    (session_runtime_options.prerun_context_folder, os.sep,
                     session_runtime_options.consolidate_manufacturers)
            else:
                session_runtime_options.context_new_vehicle_generalized_costs_file = \
                    'context_new_vehicle_prices_%d.csv' % session_runtime_options.consolidate_manufacturers

            if session_runtime_options.use_prerun_context_outputs:
                session_runtime_options.sales_share_calibration_file = \
                    '%s%scontext_sales_share_calibration_%d.csv' % \
                    (session_runtime_options.prerun_context_folder, os.sep,
                     session_runtime_options.consolidate_manufacturers)
            else:
                session_runtime_options.sales_share_calibration_file = \
                    'context_sales_share_calibration_%d.csv' % session_runtime_options.consolidate_manufacturers
            #子文件夹的名称被设置为 consolidate_0 或 consolidate_1，这取决于 consolidate_manufacturers 标志
            session_runtime_options.output_folder = session_runtime_options.output_folder_base \
                .replace(session_runtime_options.output_folder_base,
                         '%sconsolidate_%d%s' % (session_runtime_options.output_folder_base,
                                                 session_runtime_options.consolidate_manufacturers, os.sep))

            init_fail = init_omega(copy.copy(session_runtime_options))

            output_folders.append(omega_globals.options.output_folder)

            omega_globals.options.manufacturer_gigawatthour_data = manufacturer_gigawatthour_limit_data

            if not init_fail:
                if omega_globals.options.multiprocessing:
                    from omega_model import omega

                    from multiprocessing import Pool, freeze_support

                    freeze_support()

                    num_processes = min(len(omega_globals.options.MarketClass.market_classes), os.cpu_count() - 2)

                    # 你现在的位置附近（计算 num_processes 之后）
                    '''try:
                        _max = int(os.getenv("OMEGA_MAX_PROCS", "0") or "0")
                    except Exception:
                        _max = 0
                    if _max > 0:
                        num_processes = max(1, min(num_processes, _max))'''

                    if not omega_globals.options.standalone_run and not omega_globals.options.session_is_reference:
                        num_processes = \
                            max(1, int(num_processes / omega_globals.options.non_context_session_process_scaler))
                    
                    '''# honor external cap: OMEGA_MAX_PROCS 用于联合run_queue.py代码中来修改OMEGA使用的核数
                    max_env = os.getenv("OMEGA_MAX_PROCS")
                    if max_env:
                        try:
                            num_processes = max(1, min(num_processes, int(max_env)))
                        except ValueError:
                            pass'''

                    # start_time = time.time()
                    omega_globals.pool = Pool(processes=num_processes,
                                              initializer=omega.init_omega, initargs=[omega_globals.options])

                    results = []
                    for i in range(num_processes):
                        results.append(omega_globals.pool.apply_async(func=omega.poolstart,
                                                                      callback=None,
                                                                      error_callback=omega.error_callback))

                    [r.get() for r in results]

                    # print('Elapsed init time = %f' % (time.time() - start_time))

                omega_log.logwrite("Running %s:" % omega_globals.options.session_unique_name)

                if omega_globals.options.run_profiler:
                    # run with profiler
                    omega_log.logwrite('Enabling Profiler...')
                    import cProfile, pstats
                    profiler = cProfile.Profile()
                    profiler.enable()

                omega_globals.options.producer_consumer_max_iterations = \
                    max(omega_globals.options.producer_consumer_max_iterations,
                        len(omega_globals.options.MarketClass.market_classes) / 2 + 1)

                iteration_log, credit_banks = \
                    run_producer_consumer(omega_globals.pass_num, manufacturer_annual_data_table)

                omega_log.logwrite('Simulation elapsed time %.2f' % (time.time() - session_runtime_options.start_time))

                if omega_globals.options.notification_destination and omega_globals.options.notification_email \
                        and omega_globals.options.notification_password:
                    send_text(omega_globals.options.notification_destination,
                              '%s Pass %d Starting Post-processing...' % (
                                  omega_globals.options.session_unique_name, omega_globals.pass_num),
                              omega_globals.options.notification_email, omega_globals.options.notification_password)

                # postproc session
                manufacturer_annual_data_table, manufacturer_gigawatthour_limit_data = \
                    postproc_session.run_postproc(iteration_log, credit_banks)

                if omega_globals.pass_num == 0:
                    # set up data for second pass
                    manufacturer_gigawatthour_limit_df = pd.DataFrame.from_dict(manufacturer_gigawatthour_limit_data)

                    manufacturer_gigawatthour_limit_df.to_csv(
                        '%s/manufacturer_gigawatthour_limit_data_%d.csv' % (omega_globals.options.output_folder_base,
                                                                      omega_globals.options.consolidate_manufacturers),
                        columns=sorted(manufacturer_gigawatthour_limit_df.columns))

                    cert_offset = \
                        manufacturer_annual_data_table['calendar_year_cert_co2e_megagrams'] - \
                        manufacturer_annual_data_table['target_co2e_megagrams']

                    manufacturer_annual_data_table['cert_offset'] = cert_offset
                    manufacturer_annual_data_table['strategic_offset'] = cert_offset

                    # under-achievers under-achieve less, if CME < 1.0:
                    manufacturer_annual_data_table.loc[cert_offset > 0, 'strategic_offset'] = \
                        manufacturer_annual_data_table['strategic_offset'] * omega_globals.options.credit_market_efficiency

                    manufacturer_annual_data_table.to_csv('%s/manufacturer_annual_data_table_%d.csv' %
                                                          (omega_globals.options.output_folder_base,
                                                           omega_globals.options.consolidate_manufacturers),
                                                          columns=sorted(manufacturer_annual_data_table.columns),
                                                          index=False)

                # everybody out of the pool
                if omega_globals.options.multiprocessing:
                    omega_globals.pool.close()
                    omega_globals.pool.join()

                # save context calibration files
                from context.new_vehicle_market import NewVehicleMarket
                if omega_globals.options.session_is_reference and \
                        omega_globals.options.generate_context_calibration_files:
                    NewVehicleMarket.save_context_new_vehicle_generalized_costs(
                        omega_globals.options.context_new_vehicle_generalized_costs_file)#这个函数负责将当前 session 的新车广义成本数据保存到文件中
                    omega_globals.options.SalesShare.save_calibration(
                        omega_globals.options.sales_share_calibration_file)

                NewVehicleMarket.save_session_new_vehicle_generalized_costs(
                    omega_globals.options.output_folder + omega_globals.options.session_unique_name +
                    '_new_vehicle_prices.csv')#无论是否是参考 session，都会将本次运行的新车广义成本数据保存到文件中，方便后续分析和比较

            else:
                omega_log.logwrite(init_fail)
                omega_log.end_logfile("\nSession Fail")

            if omega_globals.options.run_profiler:#如果启用了性能分析
                profiler.disable()
                stats = pstats.Stats(profiler)
                omega_log.logwrite('Generating Profiler Dump...')
                stats.dump_stats('omega_profile.dmp')

            metadata_df = pd.DataFrame(omega_globals.options.inputfile_metadata)
            metadata_df = metadata_df.drop(columns=[3, 5])

            metadata_df = metadata_df.rename(columns={0: 'filepath', 1: 'filename', 2: 'checksum',
                                                      4: 'input_template_name', 6: 'version_number', 7: 'notes:'})

            metadata_df.to_csv(
                omega_globals.options.output_folder +
                f'{omega_globals.options.session_unique_name}_inputfile_metadata.csv',
                index=False, header=True)

            omega_log.end_logfile("\nSession Complete")

            if omega_globals.options.run_profiler:
                os.system('snakeviz omega_profile.dmp')

            if omega_globals.options.notification_destination and omega_globals.options.notification_email \
                    and omega_globals.options.notification_password:
                send_text(omega_globals.options.notification_destination,
                          '%s Pass %d Complete' % (omega_globals.options.session_unique_name, omega_globals.pass_num),
                          omega_globals.options.notification_email, omega_globals.options.notification_password)

        # move appropriate outputs to base output folder将最终一次模拟（如合并或不合并生产商的最后一次pass）产生的输出文件夹（如 output_folder_base/consolidate_0 或 output_folder_base/consolidate_1）中的所有内容，移动到主输出文件夹 output_folder_base 下
        file_io.move_folder_contents('%s%sconsolidate_%d' % (omega_globals.options.output_folder_base, os.sep,
                                                             consolidate[-1]),
                                     omega_globals.options.output_folder_base)

        # delete preliminary outputs if not preserving them清理临时输出文件夹
        if not omega_globals.options.save_preliminary_outputs:
            for f in output_folders:
                file_io.delete_folder(f)

    except:
        omega_log.logwrite("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
        print("### Check OMEGA log for error messages ###")
        omega_log.end_logfile("\nSession Fail")

  
if __name__ == "__main__":
    try:
        import producer

        run_omega(OMEGASessionSettings(), standalone_run=True)
    except:
        print("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
        sys.exit(-1)
