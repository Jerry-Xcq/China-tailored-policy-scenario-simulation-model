"""

**NEV credit banking module for China dual-credit system (中国双积分制度).**

This module tracks annual NEV credit balances for each OEM and provides functions for
cross-OEM NEV clearing (national settlement) and NEV-to-CAFC offset calculations.

**China Dual-Credit Semantics (中国版语义):**

1. **Only positive NEV credits are stored** - Negative balances (deficits) are NOT carried forward.

2. **Positive credits can be carried forward** up to ``NEV_CARRYFORWARD_YEARS`` (3 years).

3. **Annual carryforward discount**: Credits are discounted each year by ``NEV_CARRYFORWARD_DISCOUNT`` (0.5).
   Effective value = original_value * (0.5 ** age), where age = current_year - origin_year.

4. **Consumption order**: Credits are consumed starting with the soonest to expire (oldest age first).

5. **Deficit resolution within each year:**
   - NEV deficits are first resolved through national clearing (cross-OEM trading)
   - Remaining positive NEV credits can offset CAFC-CO2 deficits
   - Any unresolved NEV deficit is marked as non-compliant (``nev_requirement_compliant = False``)
     but is NOT stored in the bank.

6. **Key methods:**
   - ``apply_year_balance()``: Adds current year's raw balance to carry-in, stores only positive
   - ``get_available_credits()``: Returns total available credits with discount applied
   - ``use_credits()``: Consumes credits (oldest first) with discount
   - ``update_balance_after_clearing()``: Updates balance after national NEV clearing

7. **National clearing functions:**
   - ``perform_nev_clearing_for_year()``: Cross-OEM trading assuming perfect market efficiency
   - ``calc_nev_offset_for_cafc()``: Calculates NEV-to-CAFC offset conversion

Note:
    This module implements China-specific NEV credit rules. The bank never stores negative values.
    Deficits that cannot be resolved are recorded as compliance failures, not as bank entries.

"""

print('importing %s' % __file__)

from omega_model import *



MG_PER_NEV_POINT = 1.0  # 1 NEV 积分 = 1 Mg CO2（占位符）


NEV_CARRYFORWARD_YEARS = 3   # 正积分可结转年限
NEV_CARRYFORWARD_DISCOUNT = 0.5  # 每年结转折扣系数：effective = original * (0.5 ** age)


class NEVCreditBank(OMEGABase):
    """
    Tracks per-manufacturer NEV credit balances across model years.

    

    - Only positive credits are stored in the credit bank (DataFrame)
    - Negative credits (deficits) do NOT carry forward; they are cleared annually
    - Positive credits can be carried forward up to ``NEV_CARRYFORWARD_YEARS`` (3 years)
    - Annual discount: effective_value = original_value * (0.5 ** age)
    - Consumption order: oldest (soonest to expire) first

    Attributes:
        compliance_id (str): Manufacturer identifier
        credit_bank (DataFrame): Credit storage with columns [calendar_year, model_year, age, balance]
        history (list): Historical record of annual balance changes

    """

    def __init__(self, compliance_id):
        self.compliance_id = compliance_id
        # 使用 DataFrame 存储历史积分，支持年限和折扣
        self.credit_bank = pd.DataFrame(columns=['calendar_year', 'model_year', 'age', 'balance'])
        self.history = []

    @property
    def balance(self):
        """
        返回当前有效正积分余额（折扣后）。
        为兼容旧代码保留此属性。
        """
        return self.get_available_credits(apply_discount=True)

    def _get_latest_calendar_year(self):
        """获取银行中最新的 calendar_year"""
        if self.credit_bank.empty:
            return None
        return int(self.credit_bank['calendar_year'].max())

    def add_credit(self, calendar_year, balance):
        """
        Add a new positive credit entry to the bank.
        
        Args:
            calendar_year (int): year the credit is generated
            balance (float): positive credit amount (points)
        """
        if balance <= 0:
            return
        
        new_entry = pd.DataFrame({
            'calendar_year': [calendar_year],
            'model_year': [calendar_year],
            'age': [0],
            'balance': [balance]
        })
        self.credit_bank = pd.concat([self.credit_bank, new_entry], ignore_index=True)

    def update_credit_age(self, calendar_year):
        """
        Age all credits by one year, update calendar_year, and drop expired credits.
        
        Args:
            calendar_year (int): the new calendar year
        """
        if self.credit_bank.empty:
            return
        
        # 筛选上一年的记录
        last_year = calendar_year - 1
        last_year_credits = self.credit_bank[self.credit_bank['calendar_year'] == last_year].copy()
        
        if last_year_credits.empty:
            return
        
        # 增加年龄，更新日历年
        last_year_credits['age'] = last_year_credits['age'] + 1
        last_year_credits['calendar_year'] = calendar_year
        
        # 过滤已过期的积分（age > NEV_CARRYFORWARD_YEARS）和零余额
        valid_mask = (last_year_credits['age'] <= NEV_CARRYFORWARD_YEARS) & (last_year_credits['balance'] > 0)
        aged_credits = last_year_credits[valid_mask]
        
        self.credit_bank = pd.concat([self.credit_bank, aged_credits], ignore_index=True)

    def get_available_credits(self, calendar_year=None, apply_discount=True):
        """
        Get total available positive credits (with optional discount).
        
        Args:
            calendar_year (int): calendar year to query (None = latest)
            apply_discount (bool): if True, apply annual discount (0.5^age)
        
        Returns:
            float: total available credits (points)
        """
        if self.credit_bank.empty:
            return 0.0
        
        if calendar_year is None:
            calendar_year = self._get_latest_calendar_year()
        if calendar_year is None:
            return 0.0
        
        # 筛选当年有效的正积分
        mask = (self.credit_bank['calendar_year'] == calendar_year) & \
               (self.credit_bank['balance'] > 0) & \
               (self.credit_bank['age'] <= NEV_CARRYFORWARD_YEARS)
        
        valid_credits = self.credit_bank[mask]
        
        total = 0.0
        for _, row in valid_credits.iterrows():
            original = row['balance']
            age = int(row['age'])
            if apply_discount:
                effective = original * (NEV_CARRYFORWARD_DISCOUNT ** age)
            else:
                effective = original
            total += effective
        
        return total

    def use_credits(self, calendar_year, needed_points, apply_discount=True):
        """
        Use positive credits to cover a deficit.
        Credits are consumed starting from oldest (soonest to expire) first.
        
        Args:
            calendar_year (int): calendar year
            needed_points (float): amount needed (in effective/discounted terms)
            apply_discount (bool): if True, apply annual discount (0.5^age)
        
        Returns:
            float: actual effective amount used (may be less than needed)
        """
        if needed_points <= 0 or self.credit_bank.empty:
            return 0.0
        
        # 筛选当年有效的正积分
        mask = (self.credit_bank['calendar_year'] == calendar_year) & \
               (self.credit_bank['balance'] > 0) & \
               (self.credit_bank['age'] <= NEV_CARRYFORWARD_YEARS)
        
        if not mask.any():
            return 0.0
        
        # 收集有效积分并按 age 降序排序（最老的先用）
        valid_entries = []
        for idx in self.credit_bank[mask].index:
            row = self.credit_bank.loc[idx]
            valid_entries.append((idx, int(row['age']), row['balance']))
        
        # 按 age 降序排序（先到期的先用）
        valid_entries.sort(key=lambda x: -x[1])
        
        total_used_effective = 0.0
        remaining_need = needed_points
        
        for idx, age, original_balance in valid_entries:
            if remaining_need <= 1e-9:
                break
            
            if apply_discount:
                discount_factor = NEV_CARRYFORWARD_DISCOUNT ** age
                effective_available = original_balance * discount_factor
            else:
                discount_factor = 1.0
                effective_available = original_balance
            
            effective_use = min(effective_available, remaining_need)
            
            # 反算原始消耗量
            if apply_discount and discount_factor > 0:
                original_use = effective_use / discount_factor
            else:
                original_use = effective_use
            
            # 更新余额
            self.credit_bank.loc[idx, 'balance'] -= original_use
            total_used_effective += effective_use
            remaining_need -= effective_use
        
        return total_used_effective

    def apply_year_balance(self, calendar_year, nev_balance_raw):
        """
        Apply the current year's NEV balance (credits minus target) to the bank.
        First ages existing credits, then adds new positive credits if any.

        Args:
            calendar_year (int): model year being processed
            nev_balance_raw (float): raw balance (credits - target) for the current year

        Returns:
            tuple: (carry_in_balance, balance_before_trade, ending_balance)
        """
        # 先更新积分年龄
        self.update_credit_age(calendar_year)
        
        # 计算结转余额（有效值）
        carry_in = self.get_available_credits(calendar_year, apply_discount=True)
        balance_before_trade = carry_in + nev_balance_raw
        
        # 如果当年有正积分，添加到银行
        if nev_balance_raw > 0:
            self.add_credit(calendar_year, nev_balance_raw)
        
        # 最终余额（有效值）
        ending_balance = self.get_available_credits(calendar_year, apply_discount=True)
        ending_balance = max(0.0, ending_balance)

        self.history.append({'calendar_year': calendar_year,
                             'carry_in': carry_in,
                             'raw_balance': nev_balance_raw,
                             'ending_balance': ending_balance})

        return carry_in, balance_before_trade, ending_balance

    def update_balance_after_clearing(self, new_balance, calendar_year=None):
        """
        Update the NEV bank balance after national clearing.
        If credits were sold, consume from the bank accordingly.

        Args:
            new_balance (float): NEV balance after clearing (effective value, points)
            calendar_year (int): calendar year (None = use latest)
        """
        if calendar_year is None:
            calendar_year = self._get_latest_calendar_year()
        if calendar_year is None:
            return
        
        # 计算当前可用余额
        current_available = self.get_available_credits(calendar_year, apply_discount=True)
        
        # 如果清算后余额小于当前可用余额，说明卖出了积分，需要消耗
        if new_balance < current_available:
            credits_to_consume = current_available - new_balance
            self.use_credits(calendar_year, credits_to_consume, apply_discount=True)

    def use_for_cafc_offset(self, nev_points_used):
        """
        Deduct NEV credits used for CAFC-CO2 offset.

        Args:
            nev_points_used (float): NEV points consumed for CAFC offset (effective value)

        Returns:
            float: actual points deducted (may be less if not enough balance)
        """
        calendar_year = self._get_latest_calendar_year()
        if calendar_year is None:
            return 0.0
        
        return self.use_credits(calendar_year, nev_points_used, apply_discount=True)


def perform_nev_clearing_for_year(model_year, manufacturer_annual_data, nev_credit_banks):
    """
    Perform NEV national clearing for a single model year across all OEMs.
    
   

    Args:
        model_year (int): the model year to clear
        manufacturer_annual_data (list): ManufacturerAnnualData._data
        nev_credit_banks (dict): {compliance_id: NEVCreditBank}

    Returns:
        dict: clearing results keyed by compliance_id, each containing:
            - nev_surplus: 清算前正积分（点数）
            - nev_deficit: 清算前负积分（点数，正值表示缺口）
            - nev_balance_after_trade_nev: 清算后剩余 NEV 积分（点数）
            - nev_sold: 卖出的 NEV 积分（正值）
            - nev_bought: 买入的 NEV 积分（正值）
            - nev_requirement_compliant: bool
    """
    # 收集各 OEM 的 nev_balance_before_trade
    oem_balances = {}
    for mad in manufacturer_annual_data:
        if mad['model_year'] == model_year:
            cid = mad['compliance_id']
            balance = mad.get('nev_balance_before_trade', 0.0)
            oem_balances[cid] = balance

    # 计算 surplus / deficit 拆分正负积分
    surplus = {cid: max(0.0, bal) for cid, bal in oem_balances.items()}
    deficit = {cid: max(0.0, -bal) for cid, bal in oem_balances.items()}

    total_surplus = sum(surplus.values())
    total_deficit = sum(deficit.values())

    results = {}

    if total_surplus >= total_deficit:
        # 完全清算：所有负积分都能被抵消
        # 从有正积分的 OEM 按比例扣减
        if total_surplus > 0:
            ratio_used = total_deficit / total_surplus
        else:
            ratio_used = 0.0

        for cid in oem_balances:
            sold = surplus[cid] * ratio_used
            bought = deficit[cid]
            balance_after = surplus[cid] - sold  # 卖出后剩余的正积分

            results[cid] = {
                'nev_surplus': surplus[cid],
                'nev_deficit': deficit[cid],
                'nev_balance_after_trade_nev': balance_after,
                'nev_sold': sold,
                'nev_bought': bought,
                'remaining_nev_deficit': 0.0,  # 完全清算，无剩余缺口
                'nev_requirement_compliant': True
            }

            # 更新 NEV bank（剩余正积分可用于抵偿 CAFC）
            if cid in nev_credit_banks:
                nev_credit_banks[cid].update_balance_after_clearing(balance_after, model_year)
    else:
        # 不完全清算：全国正积分不足以抵消全部负积分
        # 按比例部分抵偿
        if total_deficit > 0:
            clear_ratio = total_surplus / total_deficit
        else:
            clear_ratio = 1.0

        for cid in oem_balances:
            # 正积分 OEM 全部卖出
            sold = surplus[cid]
            # 负积分 OEM 只能获得部分抵偿
            bought = deficit[cid] * clear_ratio
            remaining_deficit = deficit[cid] - bought
            
            
            balance_after = 0.0  # 所有正积分都已卖出

            # 只有 remaining_deficit == 0 才合规
            compliant = (remaining_deficit <= 1e-9)  # 使用小容差避免浮点误差

            results[cid] = {
                'nev_surplus': surplus[cid],
                'nev_deficit': deficit[cid],
                'nev_balance_after_trade_nev': balance_after,
                'nev_sold': sold,
                'nev_bought': bought,
                'remaining_nev_deficit': remaining_deficit,  # 新增：未解决的 NEV 缺口
                'nev_requirement_compliant': compliant
            }

            # 更新 NEV bank（只存正积分，不完全清算时无剩余）
            if cid in nev_credit_banks:
                nev_credit_banks[cid].update_balance_after_clearing(balance_after, model_year)

    return results


def calc_nev_offset_for_cafc(nev_balance_after_trade_nev, cafc_deficit_Mg):
    """
    Calculate how much CAFC-CO2 deficit can be offset by available NEV credits (single OEM).

    **Note:** This function only considers ONE OEM's available NEV credits.
    For cross-OEM NEV-to-CAFC offset, use ``perform_nev_cafc_clearing_for_year()``.

    Args:
        nev_balance_after_trade_nev (float): available NEV points after NEV clearing (点数)
        cafc_deficit_Mg (float): CAFC-CO2 deficit in Mg (positive value)

    Returns:
        tuple: (nev_Mg_used, remaining_cafc_deficit_Mg, remaining_nev_points)
    """
    nev_Mg_available = max(0.0, nev_balance_after_trade_nev) * MG_PER_NEV_POINT
    nev_Mg_used = min(cafc_deficit_Mg, nev_Mg_available)
    remaining_cafc_deficit = cafc_deficit_Mg - nev_Mg_used
    remaining_nev_points = max(0.0, nev_balance_after_trade_nev - nev_Mg_used / MG_PER_NEV_POINT)

    return nev_Mg_used, remaining_cafc_deficit, remaining_nev_points


def perform_nev_cafc_clearing_for_year(model_year, nev_clearing_results, cafc_deficits_after_bank):
    """
    Perform cross-OEM NEV-to-CAFC offset for a single model year.

    

    Args:
        model_year (int): the model year being processed
        nev_clearing_results (dict): results from perform_nev_clearing_for_year, keyed by compliance_id
            Each entry must contain 'nev_balance_after_trade_nev' (剩余 NEV 正积分)
        cafc_deficits_after_bank (dict): {compliance_id: deficit_Mg} CAFC-CO2 deficits after using GHG bank
            (positive values = deficit)

    Returns:
        dict: {compliance_id: {
            'own_nev_used_Mg': 本车企 NEV 抵偿量 (Mg CO2),
            'bought_nev_Mg': 从其他车企购买的 NEV (Mg CO2),
            'total_nev_Mg_used': 总 NEV 抵偿量 (Mg CO2),
            'remaining_cafc_deficit_Mg': 剩余 CAFC 缺口 (Mg CO2),
            'remaining_nev_points': 剩余 NEV 积分 (点数),
            'nev_sold_for_cafc': 卖给其他车企用于 CAFC 抵偿的 NEV (点数)
        }}
    """
    # Step 1: 收集各 OEM 的 NEV 剩余正积分和 CAFC 缺口
    oem_nev_available = {}  # 各 OEM 可用于 CAFC 抵偿的 NEV 正积分（点数）
    oem_cafc_deficit = {}   # 各 OEM 的 CAFC-CO2 缺口（Mg）

    for cid, nev_result in nev_clearing_results.items():
        oem_nev_available[cid] = max(0.0, nev_result.get('nev_balance_after_trade_nev', 0.0))

    for cid, deficit_Mg in cafc_deficits_after_bank.items():
        oem_cafc_deficit[cid] = max(0.0, deficit_Mg)

    all_oems = set(oem_nev_available.keys()) | set(oem_cafc_deficit.keys())

    # Step 2: 先让各 OEM 使用自己的 NEV 正积分
    own_nev_used = {}  # 各 OEM 使用自己 NEV 抵偿的量（Mg）
    remaining_deficit = {}  # 使用自己 NEV 后仍剩余的 CAFC 缺口（Mg）
    remaining_nev = {}  # 使用自己 NEV 后剩余的 NEV 正积分（点数）

    for cid in all_oems:
        nev_available_points = oem_nev_available.get(cid, 0.0)
        deficit_Mg = oem_cafc_deficit.get(cid, 0.0)

        nev_available_Mg = nev_available_points * MG_PER_NEV_POINT
        used_Mg = min(deficit_Mg, nev_available_Mg)

        own_nev_used[cid] = used_Mg
        remaining_deficit[cid] = deficit_Mg - used_Mg
        remaining_nev[cid] = nev_available_points - used_Mg / MG_PER_NEV_POINT if MG_PER_NEV_POINT > 0 else 0.0

    # Step 3: 跨 OEM 交易（有 CAFC 缺口的 OEM 从有剩余 NEV 的 OEM 购买）
    total_remaining_nev_Mg = sum(remaining_nev.values()) * MG_PER_NEV_POINT
    total_remaining_deficit = sum(remaining_deficit.values())

    bought_nev = {cid: 0.0 for cid in all_oems}  # 各 OEM 从其他 OEM 购买的 NEV（Mg）
    sold_nev = {cid: 0.0 for cid in all_oems}    # 各 OEM 卖给其他 OEM 的 NEV（点数）

    if total_remaining_deficit > 0 and total_remaining_nev_Mg > 0:
        # 市场完全有效，按比例分配
        if total_remaining_nev_Mg >= total_remaining_deficit:
            # 全国 NEV 正积分足够抵偿所有 CAFC 缺口
            # 有 CAFC 缺口的 OEM 全额购买
            # 有 NEV 剩余的 OEM 按比例卖出
            ratio_used = total_remaining_deficit / total_remaining_nev_Mg

            for cid in all_oems:
                # 有缺口的 OEM：购买全额
                if remaining_deficit[cid] > 1e-9: # 使用容差
                    bought_nev[cid] = remaining_deficit[cid]
                    remaining_deficit[cid] = 0.0

                # 有剩余 NEV 的 OEM：按比例卖出
                if remaining_nev[cid] > 0:
                    sold_points = remaining_nev[cid] * ratio_used
                    sold_nev[cid] = sold_points
                    remaining_nev[cid] -= sold_points
        else:
            # 全国 NEV 正积分不足，按比例部分抵偿
            clear_ratio = total_remaining_nev_Mg / total_remaining_deficit

            for cid in all_oems:
                # 有缺口的 OEM：只能获得部分抵偿
                if remaining_deficit[cid] > 1e-9: # 使用容差
                    bought = remaining_deficit[cid] * clear_ratio
                    bought_nev[cid] = bought
                    remaining_deficit[cid] -= bought

                # 有剩余 NEV 的 OEM：全部卖出
                if remaining_nev[cid] > 0:
                    sold_nev[cid] = remaining_nev[cid]
                    remaining_nev[cid] = 0.0

    # Step 4: 汇总结果
    results = {}
    for cid in all_oems:
        total_nev_used = own_nev_used[cid] + bought_nev[cid]
        results[cid] = {
            'own_nev_used_Mg': own_nev_used[cid],
            'bought_nev_Mg': bought_nev[cid],
            'total_nev_Mg_used': total_nev_used,
            'remaining_cafc_deficit_Mg': remaining_deficit[cid],
            'remaining_nev_points': remaining_nev[cid],
            'nev_sold_for_cafc': sold_nev[cid]
        }

    return results

