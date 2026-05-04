"""

**Loads NEV credit requirement ratios used for China-specific NEV compliance calculations.**

The file defines the ratio of NEV credits that must be generated relative to qualifying traditional vehicle volume
for a given model year.  Ratios are expressed as decimal fractions, e.g. ``0.25`` = 25%.

The requirements are used only during pass 1 (manufacturer-level compliance) when CME < 1.0 and NEV credits
are being evaluated in addition to EPA GHG credits.

"""

print('importing %s' % __file__)

import pandas as pd

from omega_model import *


class NEVRequirements(OMEGABase):
    """
    Provides access to NEV requirement ratios, stored as a mapping from model year to target ratio.
    """

    _data = pd.DataFrame()

    @staticmethod
    def init_from_file(filename, verbose=False):
        """
        Initialize class data from the NEV requirements input file.

        Args:
            filename (str): name of input file
            verbose (bool): enable additional console and logfile output if True

        Returns:
            List of template/input errors, else empty list on success
        """
        NEVRequirements._data = pd.DataFrame()

        input_template_name = __name__
        input_template_version = 0.1
        input_template_columns = {'model_year', 'nev_target_ratio'}

        template_errors = validate_template_version_info(filename, input_template_name, input_template_version,
                                                         verbose=verbose)

        if not template_errors:
            df = pd.read_csv(filename, skiprows=1)
            template_errors = validate_template_column_names(filename, input_template_columns, df.columns,
                                                             verbose=verbose)

        if not template_errors:
            # basic validation
            df = df[['model_year', 'nev_target_ratio']].dropna()
            df = df.sort_values('model_year').reset_index(drop=True)
            NEVRequirements._data = df

        return template_errors

    @staticmethod
    def get_target_ratio(model_year):
        """
        Get the NEV target ratio for the requested model year (use the latest available year if needed).

        Args:
            model_year (int): compliance model year

        Returns:
            float: NEV requirement ratio (0.0 if no data are available)
        """
        if NEVRequirements._data.empty:
            return 0.0

        df = NEVRequirements._data
        eligible = df[df['model_year'] <= model_year]

        if eligible.empty:#若一个都没有（也就是所有行都比当前年大），返回最早一行的比例
            return float(df['nev_target_ratio'].iloc[0])

        return float(eligible['nev_target_ratio'].iloc[-1])


if __name__ == '__main__':
    try:
        omega_globals.options = OMEGASessionSettings()
        init_fail = NEVRequirements.init_from_file(omega_globals.options.nev_requirements_file,
                                                   verbose=omega_globals.options.verbose)
        if init_fail:
            print(init_fail)
            sys.exit(-1)
        print('Loaded NEV requirements:')
        print(NEVRequirements._data)
    except:
        print("\n#RUNTIME FAIL\n%s\n" % traceback.format_exc())
        sys.exit(-1)

