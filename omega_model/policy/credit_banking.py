"""

**Routines to load initial GHG credits (in CO2e Mg), provide access to credit banking data, and handle credit
transactions, along the lines of Averaging, Bank and Trading (ABT)**

Not all features of ABT are implemented (notably, explicit between-manufacturer Trading).  Credits can be earned,
used to pay debits (model year compliance deficits) and/or may expire unused.

See Also:
    The ``manufacturers`` module and ``postproc_session.plot_manufacturer_compliance()`` for credit plotting routines.

----

**INPUT FILE FORMAT (GHG credit parameters file)**

The file format consists of a one-row template header followed by a one-row data header and subsequent data
rows.

The data represents GHG credit parameters such as credit carry-forward and carry-back year limits

File Type
    comma-separated values (CSV)

Sample Header
    .. csv-table::

       input_template_name:,ghg_credit_params,input_template_version:,0.2

Sample Data Columns
    .. csv-table::
        :widths: auto

        start_model_year,credit_carryforward_years,credit_carryback_years
        2016,5,3

Data Column Name and Description

:start_model_year:
    Start model year of the credit parameter

:credit_carryforward_years:
    Number of years the credit can carry forward to pay future debits

:credit_carryback_years:
    Number of years the credit can carry back to pay prior debits

----

**INPUT FILE FORMAT (GHG credits file)**

The file format consists of a one-row template header followed by a one-row data header and subsequent data
rows.

The data represents GHG credits that are available to manufacturers in the compliance analysis years.

File Type
    comma-separated values (CSV)

Sample Header
    .. csv-table::

       input_template_name:,ghg_credit_history,input_template_version:,0.21

Sample Data Columns
    .. csv-table::
        :widths: auto

        calendar_year,model_year,compliance_id,balance_Mg
        2019,2016,USA Motors,151139573

Data Column Name and Description

:calendar_year:
    Calendar year of the data, e.g. the analysis base year

:model_year:
    The model year of the available credits, determines remaining credit life

:compliance_id:
    Identifies the credit owner, consistent with the data loaded by the ``manufacturers`` module

:balance_Mg:
    Model year credit remaining balance in the calendar year (CO2e Mg)

----

**CODE**

"""

print('importing %s' % __file__)

from omega_model import *


class CreditInfo(OMEGABase):
    """
    **Stores GHG credit info (i.e. remaining balance, remaining years)**

    Used by GHG_credit_bank.get_credit_info() to return a list of non-expired credit and debit data

    """
    def __init__(self, remaining_balance_Mg, remaining_years, model_year):
        """
        Create GHG_credit_info object

        Args:
            remaining_balance_Mg (numeric): remaining credit balance, CO2e Mg
            remaining_years (numeric): remaining years of life before expiration
        """
        self.remaining_balance_Mg = remaining_balance_Mg
        self.remaining_years = remaining_years
        self.model_year = model_year


class CreditBank(OMEGABase):
    """
    **Provides objects and methods to handle credit transactions and provide credit bank information.**

    Each manufacturer will use its own unique credit bank object.

    **China Dual-Credit Semantics (中国版语义):**

    When used in Pass 1 with NEV enabled (China scenario), this class operates under different rules:

    1. **Only positive credits are stored** - Negative credits (deficits) are NOT carried forward.
       Each year's deficit is resolved through:
       - Using historical positive credits (oldest first → soonest to expire)
       - NEV credit offset (via ``calc_nev_offset_for_cafc()``)
       - Any remaining deficit is marked as non-compliant but NOT stored in the bank.

    2. **Positive credits can be carried forward** up to ``credit_carryforward_years`` (default 3 years).

    3. **Annual carryforward discount**: Credits are discounted each year by ``CAFC_CARRYFORWARD_DISCOUNT`` (0.9).
       Effective value = original_value * (0.9 ** age), where age = current_year - origin_year.

    4. **Consumption order**: Credits are consumed starting with the soonest to expire (oldest age first).

    5. **Key methods for China semantics:**
       - ``get_available_positive_credits_Mg()``: Returns total available positive credits (with discount)
       - ``use_positive_credits_Mg()``: Consumes positive credits to offset deficit (oldest first, with discount)
       - ``add_positive_credit_only()``: Adds only positive credits to the bank (ignores negatives)

    6. **Original US EPA methods** (``handle_credit()``, ``pay_debit()``) are still available
       but are NOT used in China Pass 1 scenarios. They support both positive and negative
       credit storage and are used in Pass 0 or non-China scenarios.

    Note:
        The ``handle_credit()`` and ``pay_debit()`` methods implement US EPA OMEGA original logic
        which allows negative credit (debit) storage and carry-back. These methods are NOT fully
        compatible with China dual-credit semantics and should NOT be used in Pass 1 China scenarios.

    """
    
    # CAFC-CO2 结转折扣系数：每年折扣 0.9
    # effective_amount = original_amount * (CAFC_CARRYFORWARD_DISCOUNT ** age)
    CAFC_CARRYFORWARD_DISCOUNT = 0.9
    def __init__(self, ghg_credit_params_filename, ghg_credits_filename, compliance_id, verbose=False):
        """

        Initialize credit bank data from input file, call after validating ghg_credits and ghg_params templates.

        Args:
            ghg_credit_params_filename (str): name of the GHG credit parameters input file
            ghg_credits_filename (str | None): name of input file containing pre-existing credit info
            compliance_id (str): name of manufacturer, e.g. 'consolidated_OEM'
            verbose (bool): enable additional console and logfile output if True

        Note:
            Raises exception on input file format error

        See Also:
            ``validate_ghg_credit_params_template()``, ``validate_ghg_credits_template()``

        """
        self.compliance_id = compliance_id
        self.credit_params = CreditBank.init_ghg_credit_params(ghg_credit_params_filename, verbose)
        self.credit_bank = CreditBank.init_ghg_credit_bank(ghg_credits_filename, compliance_id, verbose)
        self.transaction_log = pd.DataFrame()

    @staticmethod
    def init_ghg_credit_params(ghg_credit_params_filename, verbose):
        """
        Read GHG credit parameters input file.  Call after ``validate_ghg_credit_params_template()``.

        Args:
            ghg_credit_params_filename (str): name of the GHG credit parameters input file
            verbose (bool): enable additional console and logfile output if True

        Returns:
            DataFrame of credit parameters

        See Also:
            ``CreditBank.validate_ghg_credit_params_template()``

        """
        if verbose:
            omega_log.logwrite('\nInitializing credit params from %s...' % ghg_credit_params_filename)

        # read in the data portion of the input file
        credit_params = pd.read_csv(ghg_credit_params_filename, skiprows=1).set_index('start_model_year')

        return credit_params

    @staticmethod
    def init_ghg_credit_bank(ghg_credits_filename, compliance_id, verbose):
        """
        Read GHG banked credits file and return credit bank info.  Call after ``validate_ghg_credits_template()``.

        Args:
            ghg_credits_filename (str): name of input file
            compliance_id (str): manufacturer name, or 'consolidated_OEM'
            verbose (bool): enable additional console and logfile output if True

        Returns:
            DataFrame of credit bank data

        See Also:
            ``CreditBank.validate_ghg_credits_template()``

        """
        if ghg_credits_filename is not None:
            if verbose:
                omega_log.logwrite('\nInitializing credit bank from %s...' % ghg_credits_filename)

            credit_bank = pd.read_csv(ghg_credits_filename, skiprows=1)

            credit_bank = credit_bank.loc[credit_bank['compliance_id'] == compliance_id]
            credit_bank = credit_bank.rename({'balance_Mg': 'beginning_balance_Mg'}, axis='columns')
            credit_bank['ending_balance_Mg'] = credit_bank['beginning_balance_Mg']
            credit_bank['age'] = credit_bank['calendar_year'] - credit_bank['model_year'] # 例如: calendar_year=2022, model_year=2017 → age=5
        else:
            credit_bank = pd.DataFrame(columns=['age', 'calendar_year', 'model_year',
                                                'beginning_balance_Mg', 'ending_balance_Mg', 'compliance_id'])

        return credit_bank

    @staticmethod
    def validate_ghg_credit_params_template(filename, verbose):
        """
        Validate GHG credit input file template.

        Args:
            filename (str): name of input file
            verbose (bool): enable additional console and logfile output if True

        Returns:
            List of template errors, or empty list on success.

        """
        input_template_name = 'ghg_credit_params'
        input_template_version = 0.2
        input_template_columns = {'start_model_year', 'credit_carryforward_years', 'credit_carryback_years'}

        template_errors = validate_template_version_info(filename, input_template_name, input_template_version,
                                                         verbose=verbose)

        if not template_errors:
            template_errors = validate_template_column_names(filename, input_template_columns, input_template_columns,
                                                             verbose=verbose)

        return template_errors

    @staticmethod
    def validate_ghg_credits_template(filename, verbose):
        """
        Validate GHG credit input file template.

        Args:
            filename (str): name of input file
            verbose (bool): enable additional console and logfile output if True

        Returns:
            List of template errors, or empty list on success.

        """
        input_template_name = 'ghg_credit_history'
        input_template_version = 0.21
        input_template_columns = {'calendar_year', 'model_year', 'compliance_id', 'balance_Mg'}

        template_errors = validate_template_version_info(filename, input_template_name, input_template_version,
                                                         verbose=verbose)

        if not template_errors:
            df = pd.read_csv(filename, skiprows=1)

            template_errors = validate_template_column_names(filename, input_template_columns, df.columns,
                                                             verbose=verbose)

        if not template_errors:
            from producer.manufacturers import Manufacturer

            validation_dict = {'compliance_id': Manufacturer.manufacturers}

            template_errors += validate_dataframe_columns(df, validation_dict, filename)

        return template_errors

    @staticmethod
    def create_credit(calendar_year, compliance_id, beginning_balance_Mg):
        """
        Create a new GHG credit data structure.

        Args:
            calendar_year (numeric): calendar year of credit creation
            compliance_id (str): manufacturer name, or 'consolidated_OEM'
            beginning_balance_Mg (numeric): starting balance of credit in CO2e Mg

        Returns:
            DataFrame of new (age zero) credit info

        """
        new_credit = dict()
        new_credit['calendar_year'] = calendar_year
        new_credit['model_year'] = calendar_year
        new_credit['compliance_id'] = compliance_id
        new_credit['beginning_balance_Mg'] = beginning_balance_Mg
        new_credit['ending_balance_Mg'] = beginning_balance_Mg
        new_credit['age'] = 0
        new_credit = pd.DataFrame(new_credit, columns=new_credit.keys(), index=[0])
        return new_credit

    @staticmethod
    def create_credit_transaction(credit):
        """
        Create an empty (no value, no destination) credit transaction.

        Args:
            credit (Series): see GHG_credit_bank.create_credit()

        Returns:
            DataFrame of new, empty, credit transaction

        """
        new_credit_transaction = dict()
        new_credit_transaction['calendar_year'] = credit['calendar_year']
        new_credit_transaction['model_year'] = credit['model_year']
        new_credit_transaction['compliance_id'] = credit['compliance_id']
        new_credit_transaction['credit_value_Mg'] = None
        new_credit_transaction['credit_destination'] = None
        new_credit_transaction = pd.DataFrame(new_credit_transaction, columns=new_credit_transaction.keys(), index=[0])
        return new_credit_transaction

    def get_credit_param(self, model_year, param):
        """
        Get the given credit parameter for the given model year.

        Args:
            model_year (int): the model year
            param (str): the name of the paramter to retrieve

        Returns:
            The given credit parameter for the given model year.

        """
        start_years = self.credit_params.index

        model_year = max(start_years[start_years <= model_year])

        return self.credit_params.loc[model_year, param]

    def get_credit_info(self, calendar_year):
        """
        Get lists of valid (non-expired) credits and debits for the given year.

        Args:
            calendar_year (numeric): calendar year to query for credits and debits

        Returns:
            Tuple of lists of ``GHG_credit_info`` objects ([current_credits], [current_debits])

        """
        current_credits = []
        this_years_credits = self.credit_bank[self.credit_bank['calendar_year'] == calendar_year]

        # apply lifetime rules
        ghg_credits = this_years_credits[this_years_credits['ending_balance_Mg'] >= 0]
        if not ghg_credits.empty:
            for _, credit in ghg_credits.iterrows():
                credit_max_life_years = self.get_credit_param(credit['model_year'], 'credit_carryforward_years')
                if credit['age'] <= credit_max_life_years:
                    current_credits.append(
                        CreditInfo(credit['ending_balance_Mg'], credit_max_life_years - credit['age'] + 1,
                                   credit['model_year']))

        current_debits = []

        # apply lifetime rules
        ghg_debits = this_years_credits[this_years_credits['ending_balance_Mg'] < 0]
        if not ghg_debits.empty:
            for _, debit in ghg_debits.iterrows():
                debit_max_life_years = self.get_credit_param(debit['model_year'], 'credit_carryback_years')
                if debit['age'] <= debit_max_life_years:
                    current_debits.append(
                        CreditInfo(debit['ending_balance_Mg'], debit_max_life_years - debit['age'] + 1,
                                   debit['model_year']))

        return current_credits, current_debits

    def get_expiring_credits_Mg(self, calendar_year):
        """
        Get value of expiring credits in CO2e Mg for the given year.

        Args:
            calendar_year (numeric): calendar year to get expiring credits from

        Returns:
            Value of expiring credits in CO2e Mg

        """
        expiring_credits_Mg = 0
        this_years_credits = self.credit_bank[self.credit_bank['calendar_year'] == calendar_year]

        # apply lifetime rules
        ghg_credits = this_years_credits[this_years_credits['ending_balance_Mg'] >= 0]
        if not ghg_credits.empty:
            for _, credit in ghg_credits.iterrows():
                credit_max_life_years = self.get_credit_param(credit['model_year'], 'credit_carryforward_years')
                if credit['age'] == credit_max_life_years:
                    expiring_credits_Mg = credit['ending_balance_Mg']

        return expiring_credits_Mg

    def get_expiring_debits_Mg(self, calendar_year):
        """
        Get value of expiring debits in CO2e Mg for the given year.

        Args:
            calendar_year (numeric): calendar year to get expiring debits from

        Returns:
            Value of expiring debits in CO2e Mg

        """

        expiring_debits_Mg = 0
        this_years_credits = self.credit_bank[self.credit_bank['calendar_year'] == calendar_year]

        # apply lifetime rules
        ghg_debits = this_years_credits[this_years_credits['ending_balance_Mg'] < 0]
        if not ghg_debits.empty:
            for _, debit in ghg_debits.iterrows():
                debit_max_life_years = self.get_credit_param(debit['model_year'], 'credit_carryback_years')
                if debit['age'] >= debit_max_life_years:
                    expiring_debits_Mg += debit['ending_balance_Mg']

        return expiring_debits_Mg

    def update_credit_age(self, calendar_year):
        """
        Take each credit in the ``credit_bank`` and age it by one year then apply lifetime limits to drop
        expired credits and zero-value credits and debits.

        Credits and debits with zero balance are dropped silently after age zero.

        Expiration takes the form of entries in the ``transaction_log``.

            * Expiring credits with non-zero balances are marked as 'EXPIRATION' transactions and then dropped
            * Expiring debits with non-zero balances are marked as 'PAST_DUE' transactions and are then dropped

        Result is an updated ``credit_bank`` and an updated ``transaction_log``, as needed

        Args:
            calendar_year (numeric): calendar year to update credits in

        """

        # grab last years 这里只是 复制一份出来，原账本里的去年记录还留着，后面会在账本中新加今年版本
        last_years_credits = self.credit_bank[self.credit_bank['calendar_year'] == calendar_year - 1].copy()

        # last_years_credits = last_years_credits.loc[last_years_credits['credit_transfer_action'] != 'EXPIRATION']
        last_years_credits['age'] = last_years_credits['age'] + 1
        last_years_credits['calendar_year'] = calendar_year
        last_years_credits['beginning_balance_Mg'] = last_years_credits['ending_balance_Mg']

        # apply lifetime rules处理信用（正余额的条目）
        ghg_credits = last_years_credits[last_years_credits['ending_balance_Mg'] >= 0]
        if not ghg_credits.empty:
            for idx, credit in ghg_credits.iterrows():
                # log the death of non-zero value credits
                credit_max_life_years = self.get_credit_param(credit['model_year'], 'credit_carryforward_years')
                if ((credit['age'] > 0) and (credit['ending_balance_Mg'] == 0)) or \
                        credit['age'] > credit_max_life_years:
                    if credit['ending_balance_Mg'] > 0:
                        t = self.create_credit_transaction(credit)
                        t['credit_value_Mg'] = credit['ending_balance_Mg']
                        t['credit_destination'] = 'EXPIRATION'
                        self.transaction_log = pd.concat([self.transaction_log, t])
                    last_years_credits = last_years_credits.drop(idx)

        ggh_debits = last_years_credits[last_years_credits['beginning_balance_Mg'] < 0]#处理欠额（负余额的条目）
        if not ggh_debits.empty:
            for idx, debit in ggh_debits.iterrows():
                debit_max_life_years = self.get_credit_param(debit['model_year'], 'credit_carryback_years')
                if (debit['age'] > 0) and (debit['ending_balance_Mg'] == 0):
                    # silently drop zero-value debits after age 0
                    last_years_credits = last_years_credits.drop(idx)
                elif debit['age'] > debit_max_life_years:
                    # mark past due debits
                    t = self.create_credit_transaction(debit)
                    t['credit_value_Mg'] = debit['ending_balance_Mg']
                    t['credit_destination'] = 'PAST_DUE'
                    self.transaction_log = pd.concat([self.transaction_log, t])
                    last_years_credits = last_years_credits.drop(idx)

        # 必须使用 ignore_index=True 避免重复索引，否则后续 loc[idx] 可能返回多行导致报错
        self.credit_bank = pd.concat([self.credit_bank, last_years_credits], ignore_index=True)

    def handle_credit(self, calendar_year, beginning_balance_Mg):
        """
        Handle mandatory credit (and default debit) behavior.

        **WARNING: US EPA OMEGA Original Logic (美国 EPA 原始逻辑)**

        This method implements the original US EPA OMEGA credit banking logic which:
        - Allows BOTH positive credits AND negative debits to be stored in the bank
        - Supports debit carry-back (paying past debits with current credits)
        - Supports debit carry-forward (storing unpaid debits for future payment)

        **NOT compatible with China dual-credit semantics (不适用于中国双积分语义):**
        In China scenarios (Pass 1 with NEV enabled), use the following methods instead:
        - ``use_positive_credits_Mg()`` to consume historical positive credits
        - ``add_positive_credit_only()`` to store only positive credits
        Negative values should NOT be stored in the bank under China semantics.

        ---

        If the manufacturer's compliance state in the given year is over-compliance, ``beginning_balance_Mg`` will
        be positive (> 0).  In this case past under-compliance (debits) **MUST** be paid before banking any excess.
        Debits are paid starting with the oldest first and working forwards until they are all paid or the full value
        of the current credit has been paid out, whichever comes first.

        If the manufacturer's compliance state in the given year is under-compliance, ``beginning_balance_Mg`` will
        be negative (< 0).  In this case, the payment of debits is up to the programmer, there are no mandatory
        debit payment requirements.  As implemented, fresh debits are immediately paid by any available banked credits,
        so a debit will only be carried if it can't be paid in full at the time of its creation.

        Result is an updated ``credit_bank`` and an updated ``transaction_log``, as needed (via the ``pay_debit()``
        method).

        Note:

            It's possible to conceive of many different credit/debit strategies (once mandatory credit behavior has been
            handled).  In the case of OMEGA, strategic over- and under-compliance will eventually be handled by the
            year-over-year compliance tree which will allow a search of various "earn and burn" credit paths.  As such,
            it's important to leave the implimentation of such schemes out of this method and the default handling here
            allows for that.

        Args:
            calendar_year (numeric): calendar year of credit creation
            beginning_balance_Mg (numeric): starting balance of credit (or debit) in CO2e Mg

        """
        new_credit = self.create_credit(calendar_year, self.compliance_id, beginning_balance_Mg)
        self.credit_bank = pd.concat([self.credit_bank, new_credit], ignore_index=True)
        new_credit = self.credit_bank.iloc[-1].copy()  # grab credit as a Series

        this_years_credits = self.credit_bank[self.credit_bank['calendar_year'] == calendar_year].copy()#从总账本中筛选出所有与当前 calendar_year 相关的记录。这不仅包括刚刚产生的新记录，还包括从往年结转过来的、在今年依然有效的历史信用和债务。这相当于拿到了一个“当前年度的财务快照”

        # if credit is positive, see if there any debts to be paid 必须用来支付往年的碳债
        if new_credit['ending_balance_Mg'] > 0:
            debits = this_years_credits[this_years_credits['ending_balance_Mg'] < 0]#查找本年度所有未还清的历史碳债（ending_balance_Mg < 0）
            if not debits.empty:
                for _, debit in debits.iterrows():
                    if debit['ending_balance_Mg'] < 0:
                        if new_credit['ending_balance_Mg'] > 0:
                            self.pay_debit(new_credit, debit, this_years_credits, apply_discount=True)

        # if credit is negative, see if there are any credits that can pay it如果本年度为新债务（即未达标，beginning_balance_Mg < 0）
        elif new_credit['ending_balance_Mg'] < 0:
            debit = new_credit
            available_credits = this_years_credits[this_years_credits['ending_balance_Mg'] > 0].copy()
            if not available_credits.empty:
                # 按 age 降序排序（先到期先用）
                available_credits = available_credits.sort_values('age', ascending=False)
                for idx, credit in available_credits.iterrows():
                    if debit['ending_balance_Mg'] < 0:
                        if credit['ending_balance_Mg'] > 0:
                            # 从 this_years_credits 获取最新的 credit 状态
                            credit_row = this_years_credits.loc[idx].copy()
                            self.pay_debit(credit_row, debit, this_years_credits, apply_discount=True)

        self.credit_bank[self.credit_bank['calendar_year'] == calendar_year] = this_years_credits  # update bank将本年度的信用/债务快照 this_years_credits 写回 self.credit_bank，确保所有变动都被保存

    def pay_debit(self, credit, debit, this_years_credits, apply_discount=True):
        """
        Pay a debit with a credit, create a transaction in the ``transaction_log`` and update manufacter model year
        compliance status (in CO2e Mg).

        **China Carryforward Discount (中国结转折扣):**
        When ``apply_discount=True``, the effective value of historical credits is discounted by
        ``CAFC_CARRYFORWARD_DISCOUNT`` (0.9) per year of age:
        - effective_value = original_value * (0.9 ** age)
        - To pay a debit of X Mg, consume X / discount_factor from the original credit balance

        ---

        Other than expiration, paying debits is the only way credits can be consumed.

        Result is an updated ``transaction_log`` and ``ManufacturerAnnualData`` for the model years involved in the
        transaction.

        See Also:

            ``manufacturer_annual_data.ManufacturerAnnualData.update_model_year_cert_co2e_Mg()``

        Args:
            credit (Series): source credit to pay from
            debit (Series): destination debit to pay
            this_years_credits (DataFrame): DataFrame containing the valid, non-expired credits and debits in the
                current year.
            apply_discount (bool): if True, apply carryforward discount (0.9^age)

        """
        from producer.manufacturer_annual_data import ManufacturerAnnualData
        
        # 计算折扣系数
        age = int(credit['age'])
        if apply_discount:
            discount_factor = self.CAFC_CARRYFORWARD_DISCOUNT ** age
        else:
            discount_factor = 1.0
        
        # 计算有效可用金额（折扣后）
        effective_credit_available = credit['ending_balance_Mg'] * discount_factor
        
        # 计算有效支付金额（不超过负债和可用额度）
        debit_amount = abs(debit['ending_balance_Mg'])
        effective_payment = min(debit_amount, effective_credit_available)
        
        # 反算原始消耗量
        if apply_discount and discount_factor > 0:
            original_consumption = effective_payment / discount_factor
        else:
            original_consumption = effective_payment
        
        t = self.create_credit_transaction(credit)
        t['credit_value_Mg'] = original_consumption  # 原始消耗量
        t['effective_value_Mg'] = effective_payment  # 有效抵扣量
        t['discount_factor'] = discount_factor
        t['credit_destination'] = debit['model_year']
        
        credit['ending_balance_Mg'] -= original_consumption  # 原始余额减少
        debit['ending_balance_Mg'] += effective_payment  # 负债减少（有效值）
        
        self.transaction_log = pd.concat([self.transaction_log, t])
        this_years_credits.loc[credit.name] = credit  # update credit
        this_years_credits.loc[debit.name] = debit  # update debit
        ManufacturerAnnualData.update_model_year_cert_co2e_Mg(debit['model_year'], debit['compliance_id'],
                                                              -effective_payment)
        ManufacturerAnnualData.update_model_year_cert_co2e_Mg(credit['model_year'], credit['compliance_id'],
                                                              +original_consumption)

    # =====================================================================
    # China-specific methods for Pass 1 (NEV + CAFC dual-credit system)
    # These methods implement "only positive credits carry forward" semantics
    # =====================================================================

    def get_available_positive_credits_Mg(self, calendar_year, apply_discount=True):
        """
        Get the total available positive credits (in CO2e Mg) for the given year.
        Only returns positive credit balances that are still valid (not expired).

        用于中国语义：只统计正积分，负积分不结转。
        结转折扣：effective_amount = original_amount * (0.9 ** age)

        Args:
            calendar_year (int): calendar year to query
            apply_discount (bool): if True, apply annual carryforward discount (0.9^age)

        Returns:
            float: total available positive credits in CO2e Mg (with discount if enabled)
        """
        total_available = 0.0

        # 获取当年的正积分（update_credit_age 已经将所有有效积分的 calendar_year 更新为当前年）
        current_year_mask = self.credit_bank['calendar_year'] == calendar_year
        positive_mask = self.credit_bank['ending_balance_Mg'] > 0
        valid_mask = current_year_mask & positive_mask

        if not valid_mask.any():
            return 0.0

        for idx in self.credit_bank[valid_mask].index:
            credit = self.credit_bank.loc[idx]
            credit_max_life_years = self.get_credit_param(credit['model_year'], 'credit_carryforward_years')
            age = int(credit['age'])
            if age <= credit_max_life_years:
                original_balance = credit['ending_balance_Mg']
                if apply_discount:
                    # 应用结转折扣：effective = original * (0.9 ** age)
                    effective_balance = original_balance * (self.CAFC_CARRYFORWARD_DISCOUNT ** age)
                else:
                    effective_balance = original_balance
                total_available += effective_balance

        return total_available

    def use_positive_credits_Mg(self, calendar_year, needed_Mg, apply_discount=True):
        """
        Use positive credits from the bank to cover a deficit.
        Credits are consumed starting from the soonest to expire (oldest age first).

        用于中国语义：用历史正积分抵扣当年缺口。
        结转折扣：effective_amount = original_amount * (0.9 ** age)
        抵扣顺序：先到期先用（age 最大的先用）

        Args:
            calendar_year (int): calendar year
            needed_Mg (float): amount of deficit to cover (positive value, in effective/discounted terms)
            apply_discount (bool): if True, apply annual carryforward discount (0.9^age)

        Returns:
            float: actual effective amount used from bank (may be less than needed_Mg)
        """
        if needed_Mg <= 0:
            return 0.0

        total_used_effective = 0.0  # 有效抵扣量（折扣后）
        remaining_need = needed_Mg

        # 获取当年的正积分（update_credit_age 已经将所有有效积分的 calendar_year 更新为当前年）
        current_year_mask = self.credit_bank['calendar_year'] == calendar_year
        positive_mask = self.credit_bank['ending_balance_Mg'] > 0
        valid_mask = current_year_mask & positive_mask

        if not valid_mask.any():
            return 0.0

        # 筛选未过期的积分并按年龄排序（最老的先用 = 先到期先用）
        valid_credits = []
        for idx in self.credit_bank[valid_mask].index:
            credit = self.credit_bank.loc[idx]
            credit_max_life_years = self.get_credit_param(credit['model_year'], 'credit_carryforward_years')
            age = int(credit['age'])
            if age <= credit_max_life_years:
                valid_credits.append((idx, age))

        # 按年龄降序排序（age 最大的在前 = 先到期的先用）
        valid_credits.sort(key=lambda x: -x[1])

        for idx, age in valid_credits:
            if remaining_need <= 1e-9:
                break

            original_balance = self.credit_bank.loc[idx, 'ending_balance_Mg']
            
            if apply_discount:
                # 计算折扣系数
                discount_factor = self.CAFC_CARRYFORWARD_DISCOUNT ** age
                effective_available = original_balance * discount_factor
            else:
                discount_factor = 1.0
                effective_available = original_balance

            # 计算需要消耗的有效量
            effective_use = min(effective_available, remaining_need)
            
            # 反算需要从原始余额中扣除的量
            if apply_discount and discount_factor > 0:
                original_use = effective_use / discount_factor
            else:
                original_use = effective_use

            # 直接在原 DataFrame 上更新原始余额
            self.credit_bank.loc[idx, 'ending_balance_Mg'] -= original_use
            total_used_effective += effective_use
            remaining_need -= effective_use

            # 记录交易日志（记录原始消耗量和有效量）
            t = self.create_credit_transaction(self.credit_bank.loc[idx])
            t['credit_value_Mg'] = original_use  # 原始消耗量
            t['effective_value_Mg'] = effective_use  # 有效抵扣量
            t['discount_factor'] = discount_factor
            t['credit_destination'] = 'CAFC_OFFSET_%d' % calendar_year
            self.transaction_log = pd.concat([self.transaction_log, t], ignore_index=True)

        return total_used_effective

    def add_positive_credit_only(self, calendar_year, raw_credit_Mg):
        """
        Add only positive credits to the bank.
        Negative values are not stored (China semantics: negative credits don't carry forward).

        用于中国语义：负积分每年清零，只存正积分。

        Args:
            calendar_year (int): model year of credit creation
            raw_credit_Mg (float): raw credit value (may be positive or negative)

        Returns:
            float: the positive credit actually added (0 if raw_credit_Mg <= 0)
        """
        if raw_credit_Mg <= 0:
            return 0.0

        new_credit = self.create_credit(calendar_year, self.compliance_id, raw_credit_Mg)
        self.credit_bank = pd.concat([self.credit_bank, new_credit], ignore_index=True)
        return raw_credit_Mg


if __name__ == '__main__':
    try:
        if '__file__' in locals():
            print(file_io.get_filenameext(__file__))

    except:
        print("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
        sys.exit(-1)
