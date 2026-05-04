"""

**Routines to create and update yearly manufacturer compliance data.**

Manufacturer annual data is created for each compliance model year as a result of vehicle sales and certification
performance.  Compliance of a model year may be achieve retroactively through the use of credits created by future
model years.

See Also:
    The ``GHG_credits`` module, and ``postproc_session.plot_manufacturer_compliance()`` for credit plotting routines.

----

**CODE**

"""

print('importing %s' % __file__)

from omega_model import *


class ManufacturerAnnualData(OMEGABase):
    """
    Stores manufacturer annual target / achieved CO2e Mg and total cost data.

    For China dual-credit scenarios (Pass 1 with NEV enabled), additional fields are populated:

    **GHG (CAFC-CO2) Fields:**
        - ``raw_ghg_credit_Mg``: Original GHG credit (target - cert), can be positive or negative
        - ``ghg_bank_used_Mg``: Historical positive credits used to offset current year deficit
        - ``ghg_after_bank_Mg``: Balance after using historical credits (can still be negative)
        - ``ghg_after_nev_Mg``: Final balance after NEV offset (can still be negative)
        - ``nev_Mg_used_for_cafc``: Total NEV credits (converted to Mg CO2) used for CAFC offset
        - ``final_positive_credit_Mg``: Only positive credits stored in bank = max(0, ghg_after_nev)
        - ``cafc_after_nev_deficit_Mg``: Remaining deficit after all offsets = max(0, -ghg_after_nev)
        - ``cafc_nev_compliant``: True if ghg_after_nev >= 0

    **NEV Fields (NEV 比例要求清算):**
        - ``nev_actual``: Total NEV credits generated (points)
        - ``nev_target``: NEV target credits for the year (points)
        - ``nev_balance_before_trade``: Balance before national clearing = carry_in + (actual - target)
        - ``nev_surplus``: Positive balance available for sale (points)
        - ``nev_deficit``: Negative balance requiring purchase (points, stored as positive value)
        - ``nev_balance_after_trade_nev``: Balance after national NEV clearing (points)
        - ``nev_sold``: NEV credits sold to other OEMs for NEV requirement (points)
        - ``nev_bought``: NEV credits bought from other OEMs for NEV requirement (points)
        - ``remaining_nev_deficit``: Unresolved NEV deficit after clearing (points)
        - ``nev_requirement_compliant``: True if NEV requirement is met after clearing

    **NEV-to-CAFC Cross-OEM Trading Fields (NEV 抵偿 CAFC-CO2 跨车企交易):**
        - ``own_nev_used_for_cafc_Mg``: Own NEV credits used for CAFC offset (Mg CO2)
        - ``bought_nev_for_cafc_Mg``: NEV credits bought from other OEMs for CAFC offset (Mg CO2)
        - ``nev_sold_for_cafc``: NEV credits sold to other OEMs for CAFC offset (points)

    **Deficit Tracking Fields (负积分记录，用于政策分析):**
        - ``raw_ghg_deficit_Mg``: 当年 CAFC-CO2 原始负积分（正值表示缺口，0 表示无缺口）
        - ``nev_raw_balance``: 当年 NEV 原始余额 = nev_actual - nev_target（可正可负）
        - ``nev_raw_deficit``: 当年 NEV 原始负积分（正值表示缺口，0 表示无缺口）
        - ``final_cafc_deficit_Mg``: 最终 CAFC-CO2 负积分（使用所有抵偿手段后仍剩余的缺口）
        - ``final_nev_deficit``: 最终 NEV 负积分（NEV 全国清算后仍剩余的缺口，不含 CAFC 抵偿）
        - ``nev_remaining_after_cafc_offset``: NEV 抵偿 CAFC 后剩余的 NEV 正积分（可用于下年结转）

    **Note:**
        中国现行政策允许车企购买其他车企的多余 NEV 积分来抵偿本车企的 CAFC-CO2 负积分。
        NEV-to-CAFC 抵偿分两步：优先使用本车企剩余 NEV 正积分，不足时从其他车企购买。
        负积分记录用于后续对政策合规难易程度的分析。

    """
    _data = []

    @staticmethod
    def create_manufacturer_annual_data(model_year, compliance_id, target_co2e_Mg,
                                        calendar_year_cert_co2e_Mg, manufacturer_vehicle_cost_dollars,
                                        model_year_cert_co2e_megagrams=None, nev_actual=0.0, nev_target=0.0,
                                        nev_balance_before_trade=0.0):
        """
        Create initial manufacturer compliance entry for the given year.
        Final compliance state may depend on future years via credit banking.

        **唯一性保证**：(model_year, compliance_id) 是唯一键。如果记录已存在，
        将更新现有记录而不是创建重复行。

        Args:
            model_year (numeric): the compliance model year
            compliance_id (str): manufacturer name, or 'consolidated_OEM'
            target_co2e_Mg (numeric): target CO2e Mg for the model year
            calendar_year_cert_co2e_Mg (numeric): initial compliance state (CO2e Mg) of the vehicles
                produced in the model year
            manufacturer_vehicle_cost_dollars (numeric): total manufacturer vehicle cost
                (sum of vehicle sales X vehicle cost)
            model_year_cert_co2e_megagrams (numeric): manufacturer model year cert CO2e Mg, if known, else ``None``

        Returns:
            Nothing, updates class data

        """
        if not model_year_cert_co2e_megagrams:
            model_year_cert_co2e_megagrams = calendar_year_cert_co2e_Mg
        #在合规计算刚开始，还没有进行任何碳积分交易时，一个车型年的“最终”排放量自然就等于它当年的“初始”排放量。后续的计算（例如调用 update_model_year_cert_co2e_Mg 函数）会在此基础上进行修改
        ManufacturerAnnualData._data.append({'compliance_id': compliance_id, 'model_year': model_year,
                                             'target_co2e_megagrams': target_co2e_Mg,
                                             'calendar_year_cert_co2e_megagrams': calendar_year_cert_co2e_Mg,
                                             'model_year_cert_co2e_megagrams': model_year_cert_co2e_megagrams,
                                             'manufacturer_vehicle_cost_dollars': manufacturer_vehicle_cost_dollars,
                                             'nev_actual': nev_actual,
                                             'nev_target': nev_target,
                                             'nev_balance_before_trade': nev_balance_before_trade})

    @staticmethod
    def get_target_co2e_Mg(compliance_id):
        """
        Get cert target CO2e in megagrams for each model year.

        Args:
            compliance_id (str): manufacturer name, or 'consolidated_OEM'

        Returns: A list of target CO2e Mg for each model year

        """
        return [mad['target_co2e_megagrams'] for mad in ManufacturerAnnualData._data
                if mad['compliance_id'] == compliance_id]

    @staticmethod
    def get_calendar_year_cert_co2e_Mg(compliance_id):
        """
        Get the initial cert CO2e in megagrams for each calendar year, final certification may be higher or lower
        depending on credit transfers.

        Args:
            compliance_id (str): manufacturer name, or 'consolidated_OEM'

        Returns: A list of initial compliance state data (CO2e Mg) of the vehicles produced by model year

        """
        return [mad['calendar_year_cert_co2e_megagrams'] for mad in ManufacturerAnnualData._data
                if mad['compliance_id'] == compliance_id]

    @staticmethod
    def get_model_year_cert_co2e_Mg(compliance_id):
        """
        Get the final cert CO2e in megagrams for each model year, including the effect of credit transfers.

        Args:
            compliance_id (str): manufacturer name, or 'consolidated_OEM'

        Returns: A list of final achieved certification CO2e Mg for each model year, including credits transferred
        to/from other model years

        """
        return [mad['model_year_cert_co2e_megagrams'] for mad in ManufacturerAnnualData._data
                if mad['compliance_id'] == compliance_id]

    @staticmethod
    def get_total_cost_billions(compliance_id):
        """
        Get total manufacturer new vehicle cost (sum of vehicle prices times vehicle sales) for each model year, in
        billions of dollars.

        Args:
            compliance_id (str): manufacturer name, or 'consolidated_OEM'

        Returns: A list of total manufacturer vehicle costs by model year, in billions of dollars

        """
        return sum([mad['manufacturer_vehicle_cost_dollars'] / 1e9 for mad in ManufacturerAnnualData._data
                if mad['compliance_id'] == compliance_id])

    @staticmethod
    def update_model_year_cert_co2e_Mg(model_year, compliance_id, transaction_amount_Mg):
        """
        Update model year certification CO2e Mg based on the given transaction amount.  Used for credit banking.

        Args:
            model_year (numeric): the model year of the transaction
            compliance_id (str): manufacturer name, or 'consolidated_OEM'
            transaction_amount_Mg (numeric): the transaction amount, may be positive (receiving credits) or negative
                (transferring credits)

        """
        mad = [mad for mad in ManufacturerAnnualData._data
               if mad['model_year'] == model_year and mad['compliance_id'] == compliance_id]

        if mad:
            mad[0]['model_year_cert_co2e_megagrams'] += transaction_amount_Mg

    @staticmethod
    def init_manufacturer_annual_data():
        """
        Initialize the module by clear caches.

        Returns:
            Nothing, clears cached data.

        """
        ManufacturerAnnualData._data = []

        return []

    @staticmethod
    def update_nev_data(model_year, compliance_id, nev_actual, nev_target, nev_balance_before_trade,
                        overwrite_existing=True):
        """
        Update NEV summary data for the given manufacturer/model year.

        Args:
            model_year (int): compliance model year
            compliance_id (str): manufacturer id
            nev_actual (float): total NEV credits generated
            nev_target (float): NEV target credits for the year
            nev_balance_before_trade (float): available credits before any trading/clearing
            overwrite_existing (bool): if ``False`` only set values when entry is missing
        """
        mad = [mad for mad in ManufacturerAnnualData._data
               if mad['model_year'] == model_year and mad['compliance_id'] == compliance_id]

        if not mad:
            ManufacturerAnnualData.create_manufacturer_annual_data(
                model_year=model_year,
                compliance_id=compliance_id,
                target_co2e_Mg=0,
                calendar_year_cert_co2e_Mg=0,
                manufacturer_vehicle_cost_dollars=0,
                model_year_cert_co2e_megagrams=0,
                nev_actual=nev_actual,
                nev_target=nev_target,
                nev_balance_before_trade=nev_balance_before_trade)
            return

        record = mad[0]
        if overwrite_existing or 'nev_actual' not in record:
            record['nev_actual'] = nev_actual
        if overwrite_existing or 'nev_target' not in record:
            record['nev_target'] = nev_target
        if overwrite_existing or 'nev_balance_before_trade' not in record:
            record['nev_balance_before_trade'] = nev_balance_before_trade

    @staticmethod
    def update_nev_clearing_results(model_year, compliance_id, nev_clearing_result):
        """
        Update NEV clearing results after national settlement.

        Args:
            model_year (int): compliance model year
            compliance_id (str): manufacturer id
            nev_clearing_result (dict): result from perform_nev_clearing_for_year containing:
                - nev_surplus, nev_deficit, nev_balance_after_trade_nev
                - nev_sold, nev_bought, remaining_nev_deficit, nev_requirement_compliant
                - own_nev_used_for_cafc_Mg: 本车企 NEV 用于 CAFC 抵偿的量（Mg CO2）
                - bought_nev_for_cafc_Mg: 从其他车企购买 NEV 用于 CAFC 抵偿的量（Mg CO2）
                - nev_sold_for_cafc: 卖给其他车企用于 CAFC 抵偿的 NEV 积分（点数）
        """
        mad = [mad for mad in ManufacturerAnnualData._data
               if mad['model_year'] == model_year and mad['compliance_id'] == compliance_id]

        if not mad:
            return

        record = mad[0]
        # NEV 清算（满足 NEV 比例要求）相关字段
        record['nev_surplus'] = nev_clearing_result.get('nev_surplus', 0.0)
        record['nev_deficit'] = nev_clearing_result.get('nev_deficit', 0.0)
        record['nev_balance_after_trade_nev'] = nev_clearing_result.get('nev_balance_after_trade_nev', 0.0)
        record['nev_sold'] = nev_clearing_result.get('nev_sold', 0.0)
        record['nev_bought'] = nev_clearing_result.get('nev_bought', 0.0)
        record['remaining_nev_deficit'] = nev_clearing_result.get('remaining_nev_deficit', 0.0)
        record['nev_requirement_compliant'] = nev_clearing_result.get('nev_requirement_compliant', True)

        # NEV 抵偿 CAFC-CO2 相关字段（跨车企交易）
        record['own_nev_used_for_cafc_Mg'] = nev_clearing_result.get('own_nev_used_for_cafc_Mg', 0.0)
        record['bought_nev_for_cafc_Mg'] = nev_clearing_result.get('bought_nev_for_cafc_Mg', 0.0)
        record['nev_sold_for_cafc'] = nev_clearing_result.get('nev_sold_for_cafc', 0.0)

        # NEV 负积分记录字段（用于政策分析）
        nev_actual = record.get('nev_actual', 0.0)
        nev_target = record.get('nev_target', 0.0)
        nev_raw_balance = nev_actual - nev_target
        record['nev_raw_balance'] = nev_raw_balance  # 当年 NEV 原始余额（可正可负）
        record['nev_raw_deficit'] = abs(min(0.0, nev_raw_balance))  # 当年 NEV 原始负积分
        record['final_nev_deficit'] = nev_clearing_result.get('remaining_nev_deficit', 0.0)  # NEV 全国清算后剩余缺口
        record['nev_remaining_after_cafc_offset'] = nev_clearing_result.get('nev_remaining_after_cafc_offset', 0.0)  # NEV 抵偿 CAFC 后剩余的 NEV 正积分

    @staticmethod
    def update_cafc_nev_results(model_year, compliance_id, raw_ghg_credit, ghg_bank_used,
                                ghg_after_bank, ghg_after_nev, nev_Mg_used_for_cafc,
                                final_positive_credit, cafc_nev_compliant):
        """
        Update CAFC-CO2 results after GHG bank usage and NEV offset.

        This method records the complete GHG credit flow for the China dual-credit system:
        1. raw_ghg_credit: Original GHG credit (target - cert), can be positive or negative
        2. ghg_bank_used: Historical positive credits used to offset current deficit
        3. ghg_after_bank: Balance after using historical credits (can still be negative)
        4. ghg_after_nev: Final balance after NEV offset (can still be negative)
        5. final_positive_credit: Only positive credits stored in bank (max(0, ghg_after_nev))

        Args:
            model_year (int): compliance model year
            compliance_id (str): manufacturer id
            raw_ghg_credit (float): original GHG credit = target_Mg - cert_Mg (positive=surplus, negative=deficit)
            ghg_bank_used (float): historical positive credits consumed to offset deficit
            ghg_after_bank (float): GHG balance after using historical positive credits
            ghg_after_nev (float): final GHG balance after NEV offset
            nev_Mg_used_for_cafc (float): NEV credits (in Mg CO2) used for CAFC offset
            final_positive_credit (float): positive credit stored in bank (only if ghg_after_nev > 0)
            cafc_nev_compliant (bool): True if ghg_after_nev >= 0
        """
        mad = [mad for mad in ManufacturerAnnualData._data
               if mad['model_year'] == model_year and mad['compliance_id'] == compliance_id]

        if not mad:
            return

        record = mad[0]
        # GHG 相关字段（完整的积分流转记录）
        record['raw_ghg_credit_Mg'] = raw_ghg_credit  # 当年原始 GHG 积分（可正可负）
        record['ghg_bank_used_Mg'] = ghg_bank_used  # 使用的历史正积分
        record['ghg_after_bank_Mg'] = ghg_after_bank  # 使用历史正积分后的余额（可正可负）
        record['ghg_after_nev_Mg'] = ghg_after_nev  # 使用 NEV 抵扣后的最终余额（可正可负）
        record['nev_Mg_used_for_cafc'] = nev_Mg_used_for_cafc  # NEV 抵扣量（Mg CO2）
        record['final_positive_credit_Mg'] = final_positive_credit  # 最终存入银行的正积分
        record['cafc_after_nev_deficit_Mg'] = abs(min(0.0, ghg_after_nev))  # 剩余缺口（正值表示不合规）
        record['cafc_nev_compliant'] = cafc_nev_compliant  # CAFC-CO2 合规标记

        # 负积分记录字段（用于政策分析）
        record['raw_ghg_deficit_Mg'] = abs(min(0.0, raw_ghg_credit))  # 当年 CAFC-CO2 原始负积分
        record['final_cafc_deficit_Mg'] = abs(min(0.0, ghg_after_nev))  # 最终 CAFC-CO2 负积分

    @staticmethod
    def get_record(model_year, compliance_id):
        """
        Get the record for the given model year and compliance id.

        Args:
            model_year (int): model year
            compliance_id (str): manufacturer id

        Returns:
            dict or None: the record if found
        """
        for mad in ManufacturerAnnualData._data:
            if mad['model_year'] == model_year and mad['compliance_id'] == compliance_id:
                return mad
        return None


if __name__ == '__main__':
    try:
        if '__file__' in locals():
            print(file_io.get_filenameext(__file__))

        # set up global variables:
        omega_globals.options = OMEGASessionSettings()

        from manufacturers import Manufacturer  # required by vehicles

    except:
        print("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
        sys.exit(-1)
