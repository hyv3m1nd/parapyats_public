"""
@author Ben Hsieh

Para- is the Greek prefix for "beside/next to." Parapyats is therefore a framework used alongside the pyats testing framework.
Building on top of the sste framework, parapyats is a test automation framework that holds sste framework's variables in the ParentTest class and automatically applies them to sste's functions.
This allows programmers to use the sste framework's functions without thinking about its data structures.
At the core of this framework are ParentTest.start_step(), ParentTest.troubleshootable_step() (which is essentially ParentTest.start_step() capable of running further troubleshooting commands if the ste fails), ParentTest.run_cmds(), and ParentTest.run_on_router().
For specific use cases, please refer to bgp_tests.py, ecmp_tests.py, and functional_tests.py, each of which uses its specific Test class.

Note: this framework is built on sste frameworks, which are proprietary and unavailable here.
"""
import cmd
import sys, inspect

sys.path.append("cafykit/lib/")
import copy

from pyats import aetest
from pyats.aetest.loop import Iteration
from pyats.easypy import run
from ats.log.utils import banner
import logging
import sste_common, sste_exr, sste_cxr, sste_trigger, sste_cli_keys, sste_spitfire, sste_tgn

import yaml, pdb, json
from texttable import Texttable
import re, random, collections
from functools import reduce
from time import time, sleep
from typing import Any, Union, Dict, List, Tuple
import operator


try:
    cli_mapping = sste_cli_keys.cli_mapping
    cli_parser_exclude_keys = sste_cli_keys.cli_parser_exclude_keys
    cli_parser_non_matching_keys = sste_cli_keys.cli_parser_non_matching_keys

except ImportError:
    cli_parser_exclude_keys = {}
    cli_parser_non_matching_keys = {}
    cli_mapping = {}


def tree():
    return collections.defaultdict(tree)


def error_to_string(e):
    return f"{type(e).__name__}: {', '.join(e.args)}"


def print_(text, end="\n"):
    if isinstance(text, str):
        print(text, end=end)
    else:
        try:
            text.keys()
            print(json.dumps(text, indent=4), end=end)
        except Exception as e:
            try:
                text[0]
                print(json.dumps(text, indent=4), end=end)
            except Exception as e:
                print(str(text), end=end)
    sys.stdout.flush()


def get_time(time_now):
    multiplier = 1
    pattern = "(\d*).*s"
    time_now = str(time_now)
    if time_now.endswith("ms"):
        multiplier = 0.001
        pattern = "(\d*).*ms"
    elif not time_now.endswith("s"):
        time_now = str(time_now) + "s"
    result = re.search(pattern, time_now)
    if result:
        return int(result.group(1)) * multiplier
    return 0


def time_to_string(seconds):
    days, hours, minutes, seconds = (
        int(seconds / 86400),
        int((seconds % 86400) / 3600),
        int((seconds % 3600) / 60),
        int(seconds % 60),
    )
    days = f"{days}d" if days else ""
    hours = f"{hours}h" if hours else ""
    minutes = f"{minutes}m" if minutes else ""
    seconds = f"{seconds}s" if seconds else ""

    time_string = days + hours + minutes + seconds
    if not time_string:
        time_string = "0s"
    return time_string


def select_x(my_list: list, x: int):
    random.shuffle(my_list)
    return my_list[:x]


def unique(sequence: list):
    """
    preserves the order of list elements but removes duplicates
    """
    seen = set()
    return [x for x in sequence if not (x in seen or seen.add(x))]


class Parent_Test:
    testscript = None
    script_args = None
    test_data = None
    testbed = None
    test_data = None
    timing = None
    section = None
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    steps = None
    step = (None,)
    testcase = ""
    automation_is_passing = True  # used for flow control
    testcase_passed = True  # used for troubleshooting at the end of a testcase
    step_passed = True  # used in troubleshootable_step() to troubleshoot a step

    @classmethod
    def initialize(cls):
        """
        Initializes the class variables used by many of the functions.
        This should be called at the beginning of the common setup in every test file.
        """
        cls.testscript = None
        cls.script_args = None
        cls.test_data = None
        cls.testbed = None
        cls.test_data = None
        cls.timing = None
        cls.section = None
        cls.logger = logging.getLogger(__name__)
        cls.logger.setLevel(logging.INFO)
        cls.steps = None
        cls.step = (None,)
        cls.testcase = ""
        cls.automation_is_passing = True  # used for flow control
        cls.testcase_passed = True  # used for troubleshooting at the end of a testcase
        cls.step_passed = True  # used in troubleshootable_step() to troubleshoot a step

    @classmethod
    def set_logger(cls, title):
        cls.logger = logging.getLogger(title)
        cls.logger.setLevel(logging.INFO)

    @classmethod
    def set_testcase(cls, testcase):
        cls.set_logger(testcase)
        cls.testcase = testcase

    @classmethod
    def set_steps(cls, steps):
        cls.steps = copy.copy(steps)

    @classmethod
    def set_testscript(cls, testscript):
        if "timing" not in testscript:
            testscript.parameters["timing"] = tree()
        if "script_args" not in testscript:
            testscript.parameters["script_args"] = tree()
        cls.testscript = testscript
        cls.set_script_args(testscript.parameters["script_args"])
        cls.set_timing(testscript.parameters["timing"])

    @classmethod
    def set_script_args(cls, script_args):
        cls.script_args = script_args

    @classmethod
    def set_test_data(cls, test_data):
        cls.test_data = test_data

    @classmethod
    def set_testbed(cls, testbed):
        cls.testbed = testbed

    @classmethod
    def set_timing(cls, timing):
        cls.timing = timing

    @classmethod
    def set_section(cls, section):
        cls.section = section

    @classmethod
    def set_params(
        cls,
        testscript=None,
        script_args=None,
        test_data=None,
        testbed=None,
        timing=None,
        section=None,
        testcase=None,
        steps=None,
    ):
        """
        Stores the variables pyats and sste frameworks need to class variables.
        """
        if testscript is not None:
            cls.set_testscript(testscript)
        if script_args is not None:
            cls.set_script_args(script_args)
        if test_data is not None:
            cls.set_test_data(test_data)
        if testbed is not None:
            cls.set_testbed(testbed)
        if timing is not None:
            cls.set_timing(timing)
        if section is not None:
            cls.set_section(section)
        if testcase is not None:
            cls.set_testcase(testcase)
        if steps is not None:
            cls.set_steps(steps)

        if "script_args" in cls.__dict__.keys():
            cls.testcase_passed = True
            cls.troubleshoot_categories = []

    @classmethod
    def print_params(cls):
        print_(cls.__dict__)

    @classmethod
    def print_(cls, text):
        print_(text)

    @classmethod
    def log(cls, message: str, log_type="info"):
        if cls.logger is None:
            print_(message)
        else:
            if log_type == "info":
                cls.logger.info(message)
            elif log_type == "warning":
                cls.logger.warning(message)
            elif log_type == "error":
                cls.logger.error(message)
            elif log_type == "debug":
                cls.logger.debug(message)

    @classmethod
    def passed(cls, explanation: str):
        cls.step_passed = True

        if cls.step is not None:
            step = cls.step
            cls.step = None
            step.passed(explanation)
            return explanation
        else:
            cls.log(explanation)
            return explanation

    @classmethod
    def passx(cls, explanation: str):
        cls.step_passed = True

        if cls.step is not None:
            step = cls.step
            cls.step = None
            step.passx(explanation)
            return explanation
        else:
            cls.log(explanation)
            return explanation

    @classmethod
    def failed(cls, explanation: str, troubleshoot_categories: List[str] = []):
        cls.step_passed = False
        cls.testcase_passed = False
        cls.automation_is_passing = False

        if cls.step is not None:
            step = cls.step
            cls.step = None
            step.failed(explanation)
            return False

        else:
            cls.log(explanation, "warning")
            return False

    @classmethod
    def error(cls, explanation: str, troubleshoot_categories: List[str] = []):
        cls.step_passed = False
        cls.testcase_passed = False
        cls.automation_is_passing = False

        if cls.step is not None:
            step = cls.step
            cls.step = None
            step.failed(explanation)
            return False

        else:
            cls.log(explanation, "error")
            return False

    @classmethod
    def skipped(cls, explanation: str):
        cls.step_passed = True

        if cls.step is not None:
            step = cls.step
            cls.step = None
            step.skipped(explanation)
            return True

        else:
            cls.log(explanation)
            return True

    @classmethod
    def wait(cls, seconds):
        cls.log(f"Wait {seconds} seconds")
        for i in range(1, int(seconds / 10) + 1):
            sleep(10)
            print_(f"Waited {time_to_string(i*10)}")
        if seconds % 10:
            sleep(seconds % 10)
            print_(f"Waited {time_to_string(seconds)}")

    @classmethod
    def count_lines(
        cls, raw_cmd, criteria: Union[str, list] = None, display_full_output=True
    ):
        """
        Given a cmd, if display_full_output is true, run it as is first.
        Then, run it with " | utility wc -l", parse the output, and turn the count into an int.
        """
        if display_full_output:
            cls.run_cmds(raw_cmd)

        if criteria is not None:
            if isinstance(criteria, list):
                criteria = " | ".join(criteria)

        cmd = (
            f"{raw_cmd} | utility wc -l"
            if criteria is None
            else f"{raw_cmd} | {criteria} | utility wc -l"
        )

        parsed_output = cls.run_cmds(cmd, "utility_wc_l.textfsm")

        count = int(parsed_output["count"])
        cls.log(f"Number of lines counted: {count}")
        return count

    @classmethod
    def verify(cls, boolean, boolean_means: str):
        """
        Checks if the boolean is True.
        Print the explanation, followed by True/False, referring to the boolean.
        If the boolean is False, fail the step.
        """
        if boolean:
            cls.log(f"{boolean_means}: True")
            return True
        else:
            return cls.failed(f"{boolean_means}: False")

    @classmethod
    def verify_count_lines(
        cls, raw_cmd: str, comparator: str, target: int, explanation: str, criteria=None
    ):
        """
        comparator options: '>', '<', '>=', '<=', '==', '!='.
        explanation explains the purpose of the comparison.
        """
        count = cls.count_lines(raw_cmd, criteria)

        comparison_options = {
            ">": operator.gt,
            "<": operator.lt,
            ">=": operator.ge,
            "<=": operator.le,
            "==": operator.eq,
            "!=": operator.ne,
        }
        comparison_function = comparison_options[comparator]

        target = int(target)
        criteria_met = comparison_function(count, target)

        numerical_explanation = f"Actual lines ({count}) {comparator} target lines ({target}): {criteria_met}"
        cls.log(numerical_explanation)

        return cls.verify(criteria_met, explanation)

    @classmethod
    def verify_line_count(
        cls,
        raw_cmd: str,
        criteria: Union[str, list] = None,
        comparator: str = "==",
        target: int = -1,
        explanation: str = "",
    ):
        """
        This is verify_count_lines with some parameters moved around. It is meant to replace verify_count_lines
        comparator options: '>', '<', '>=', '<=', '==', '!='.
        explanation explains the purpose of the comparison.
        """
        count = cls.count_lines(raw_cmd, criteria)

        comparison_options = {
            ">": operator.gt,
            "<": operator.lt,
            ">=": operator.ge,
            "<=": operator.le,
            "==": operator.eq,
            "!=": operator.ne,
        }
        comparison_function = comparison_options[comparator]

        target = int(target)
        criteria_met = comparison_function(count, target)

        numerical_explanation = f"Actual lines ({count}) {comparator} target lines ({target}): {criteria_met}"
        cls.log(numerical_explanation)

        return cls.verify(criteria_met, explanation)

    @classmethod
    def start_step_stable_1_11_2023(
        cls, step_txt, continue_=False, error_troubleshoot_categories: List[str] = []
    ):
        """
        Usage:
        Test.start_step(step_txt="step description", continue_=True) \\\n
            (step_function)(step_parameters)
        """
        step_txt = cls._format(step_txt)

        def inner(func):
            def wrapper(*args, **kwargs):
                with cls.steps.start(step_txt, continue_=continue_) as step:
                    cls.step = step
                    try:
                        output = func(*args, **kwargs)
                        cls.step = None
                        return output
                    except Exception as e:
                        fail_message = error_to_string(e)
                        cls.error(
                            fail_message,
                            troubleshoot_categories=error_troubleshoot_categories,
                        )

            return wrapper

        return inner

    @classmethod
    def start_step(
        cls,
        step_txt: str,
        continue_: bool = False,
        ixia_goal: str = "skip",
        error_troubleshoot_categories: List[str] = [],
    ):
        """
        Parameters
        ----------
        step_txt: str

        ixia_goal: str
            options: show (default, just show without checking), lossless, lossy, skip (everything else)

        Usage
        -----
        Test.start_step(step_txt="step description", continue_=True) \\\n
            (step_function)(step_parameters)
        """
        step_txt = cls._format(step_txt)

        def inner(func):
            def wrapper(*args, **kwargs):
                output = None
                with cls.steps.start(step_txt, continue_=continue_) as step:
                    cls.step = step
                    try:
                        output = func(*args, **kwargs)
                        if ixia_goal != "skip":
                            cls.sanity_traffic_check(cls, ixia_goal=ixia_goal)
                        cls.step = None
                        return output
                    except Exception as e:
                        if ixia_goal != "skip":
                            cls.sanity_traffic_check(cls, ixia_goal=ixia_goal)
                        fail_message = error_to_string(e)
                        cls.error(
                            fail_message,
                            troubleshoot_categories=error_troubleshoot_categories,
                        )

            return wrapper

        return inner

    @classmethod
    def update_troubleshooting_categories(
        cls,
        troubleshoot_categories: List[str],
        override_existing_categories: bool = False,
    ):
        """
        Adds troubleshoot_categories to the list of troubleshooting categories.
        """
        if isinstance(troubleshoot_categories, str):
            troubleshoot_categories = [troubleshoot_categories]

        if override_existing_categories:
            cls.troubleshoot_categories = troubleshoot_categories

        else:
            existing_troubleshoot_categories = cls.troubleshoot_categories
            cls.troubleshoot_categories = unique(
                existing_troubleshoot_categories + troubleshoot_categories
            )

    @classmethod
    def troubleshootable_step(
        cls,
        step_txt: str,
        continue_: bool = False,
        troubleshoot_categories: Union[bool, str, List[str]] = True,
        additional_troubleshooting_cmds: list = [],
    ) -> Any:
        """
        Starts a step titled <step_txt> and runs the step_function using the third set of parameters.
        Attempts to troubleshoot it based on troubleshoot_categories if the step fails, before carrying on with the rest of the test.

        First Set of Parameters
        -----------------------
        step_txt: str
            The title of this step

        continue_: bool (default: False)
            Whether to run subsequent non-troubleshooting steps if the current step fails

        troubleshoot_categories: str, List[str], bool (default: True)
            One or list of strings reflecting troubleshooting categories.
            The options are "ixia" and troubleshoot()'s troubleshoot_specifications keys.
            If interpreted as False, disable troubleshooting, even if further refined during step_function.
            Defaults to True (enables troubleshooting but does not further define troubleshooting categories).
            If left as True, enable debugging requires debugging categories will then have to be further updated during the execution of the step_function.
            If "ixia" is included, show ixia traffic stats.
            Note: this list can be further refined during the execution of step_function by calling update_troubleshooting_categories().
            Note: if this variable is not True, a string, or a non-empty list, disable troubleshooting and do not update cls.troubleshoot_categories (cls.troubleshoot_categories can still be updated in step_function but will not be used if this step fails).

        Second Set of Parameters
        ------------------------
        step_function: callable
            The function to execute. Can use a step-finishing function (cls.passed()/passx()/skipped()/failed()/error()) to finish execution.
            Returns the output of this function.

        Third Set of Parameters
        -----------------------
        args, kwargs: Any
            Arguments to pass into step_function

        Output
        ------
        Anything the step_function returns


        Example
        -------
        output = Parent_Test.troubleshootable_step(step_txt="Show PFC logs", continue_=True, troubleshoot_categories=["ixia", "pfc"]) \\\n
            (Parent_Test.run_cmds)("show log | inc pfc")
        # step_txt="Show PFC logs"                     --> Starts a step called "Show PFC logs."
        # (Parent_Test.run_cmds)("show log | inc pfc") --> Acquires the output of "show log | inc pfc".
        # output = Parent_Test.troubleshootable_step() --> Saves the output in a variable called output.
        # troubleshoot_categories=["ixia", "pfc"]      --> If the step fails, displays ixia stats and runs ixia and pfc troubleshooting commands, as defined in troubleshoot().
        # continue_=True                               --> Regardless of pass/fail, continue executing subsequent test steps.
        """
        cls.step_passed = True

        if isinstance(troubleshoot_categories, str):
            troubleshoot_categories = [troubleshoot_categories]

        if troubleshoot_categories == True:
            enable_troubleshooting = True
            cls.troubleshoot_categories = []

        elif isinstance(troubleshoot_categories, list):
            enable_troubleshooting = True if troubleshoot_categories else False
            cls.troubleshoot_categories = troubleshoot_categories

        else:
            enable_troubleshooting = False

        step_txt = cls._format(step_txt)

        def inner(step_function: callable):
            def wrapper(*args, **kwargs):
                output = None
                continue__ = continue_ or enable_troubleshooting
                with cls.steps.start(step_txt, continue_=continue__) as main_step:
                    cls.step = main_step
                    try:
                        output = step_function(*args, **kwargs)
                        cls.step = None
                        return output
                    except Exception as e:
                        fail_message = error_to_string(e)
                        cls.error(fail_message)

                if not cls.step_passed:
                    if enable_troubleshooting and (
                        cls.troubleshoot_categories or additional_troubleshooting_cmds
                    ):
                        with cls.steps.start(
                            "Collect data for troubleshooting", continue_=continue_
                        ) as troubleshooting_step:
                            cls.step = troubleshooting_step
                            try:
                                cls.troubleshoot(
                                    troubleshoot_level="failed",
                                    additional_specifications_to_gather=additional_troubleshooting_cmds,
                                )
                                cls.failed(
                                    f"troubleshooting logs collected for {', '.join(troubleshoot_categories)}"
                                )
                            except Exception as e:
                                fail_message = error_to_string(e)
                                cls.error(fail_message)

                    elif not continue_:
                        with cls.steps.start(
                            "Stop test section", continue_=False
                        ) as troubleshooting_step:
                            cls.step = troubleshooting_step
                            cls.failed("Test section stopped")

            return wrapper

        return inner

    @classmethod
    def run_on_router(cls, router: str, alias: str = None, via: str = "") -> Any:
        """
        Ssh into the specified router, run the inner function, and ssh back to the oiginal router.

        First Set of Parameters
        -----------------------
        router: str
            The name of the router, as defined in the testbed

        alias: str (default: None)
            Name of the ssh session. Defaults to the name of the router.
            If an ssh session by the same alias already exists, switch to that ssh session and do not start a new ssh session.
            If an ssh session by the same alias does not already exist, create a new ssh session.
            Note: if an alias is provided and an ssh session by that alias already exists, switch to that ssh session regardless of whether the router matches.

        via: str (default: "")
            # TODO provide clearer documentation
            The via variable used in sste_common._get_connection()

        Second Set of Parameters
        ------------------------
        func: callable
            The function to execute on the new ssh session.
            Returns the output of this function.

        Third Set of Parameters
        -----------------------
        args, kwargs: Any
            Arguments to pass into func

        Output
        ------
        Anything func returns

        Example
        -------
        Test.run_on_router(router="ctsw-8812-1", alias="spine 1 ssh connection 1") \\\n
            (run_cmds)("show logging")
        """

        def inner(func: callable):
            def wrapper(*args, **kwargs):
                if router is not None:
                    original_router = cls.test_data["UUT"]
                    original_alias = cls.script_args["current_alias"]
                    try:
                        cls.switch_router(router, alias=alias, via=via)
                    except ConnectionError as e:
                        cls.log(f"Cannot ssh into {router}", "warning")
                        cls.test_data["UUT"] = original_router
                        return None

                    else:
                        try:
                            # verify that we are actually on the new router
                            output = func(*args, **kwargs)

                        except Exception as e:
                            fail_message = error_to_string(e)
                            cls.log(fail_message, "warning")
                            output = None

                        cls.switch_router(original_router, alias=original_alias)
                        if output is None:
                            output = True
                        return output

                else:
                    return func(*args, **kwargs)

            return wrapper

        return inner

    @classmethod
    def switch_router(cls, router: str = None, alias: str = None, via: str = ""):
        """
        If router is None, attempt to ssh into the original router.
        """
        if "uut_list" not in cls.script_args:
            cls.script_args["uut_list"] = {}

        if router is None:
            if "initial_uut" in cls.test_data.keys():
                router = cls.test_data["initial_uut"]

        if alias is None:
            alias = router

        alias_exists = alias in cls.script_args["uut_list"]
        if alias_exists:
            session_data = cls.script_args["uut_list"][alias]
            cls.script_args["uut"] = session_data["session"]
            cls.script_args["UUT"] = session_data["device"]
            cls.script_args["sste_device"] = session_data["device"]
            cls.script_args["current_alias"] = alias

            cls.log(f"Acquired pre-established ssh connection to {alias}")
            return True

        else:
            need_to_switch_router = alias != cls.script_args["current_alias"]

            if need_to_switch_router:
                new_uut = sste_common._get_connection(
                    cls.script_args, cls.testbed, router, {"via": via}
                )
                cls.script_args["uut"] = new_uut
                cls.script_args["current_alias"] = alias
                cls.script_args["uut_list"][alias] = {
                    "session": new_uut,
                    "device": router,
                }
                cls.log(f"Connected to {router}")
                return True

            else:
                cls.log("No need to switch router")
                return True

    @classmethod
    def _connect_to_uut(cls, connect_via: str = None):
        nest_data = {
            "user_id": cls.test_data["submitter"],
            "testbed": "CET_CVT",
            "trigger": "cvtauto",
            "trigger_prefix": "cetcvt",
        }

        if connect_via is not None:
            cls.script_args["sste_connect_via"] = connect_via

        elif "connect_via" in cls.test_data:
            cls.script_args["sste_connect_via"] = cls.test_data["connect_via"]

        cls.switch_router(cls.test_data["UUT"])
        """
        cls.script_args['uut'] = sste_common._get_connection(
            cls.script_args, cls.testbed, cls.test_data['UUT'])
        cls.script_args["current_alias"] = cls.test_data['UUT']
        
        cls.script_args['uut_list'][cls.test_data['UUT']] = cls.script_args['uut']
        """

        args = {"sste_commands": "['show configuration commit changes last 2']"}
        sste_common.exec_commands(args, cls.script_args)
        sste_common.get_version_info(cls.script_args, cls.testbed)
        sste_common.init_nest_data(nest_data, cls.script_args, cls.testbed)

        return True

    @classmethod
    def connect_to_uut(cls, connect_via: str = None, attempts: int = 30):
        cls.test_data["initial_uut"] = cls.test_data["UUT"]

        attempts = int(attempts)
        attempts = 1 if attempts < 1 else attempts

        target_router = cls.test_data["UUT"]

        for attempt in range(1, attempts + 1):
            print_(f"Attempt #{attempt} to connect to {target_router}")
            try:
                connected = cls._connect_to_uut(connect_via)
                if connected:
                    return True

            except Exception as e:
                print_(f"Attempt #{attempt} failed")
                if attempt < attempts:
                    cls.wait(10)

        return cls.failed(f"Cannot ssh into {target_router}")

    @classmethod
    def connect_to_tgn(cls):
        if "tgn_api" not in cls.test_data:
            return cls.failed(
                "Traffic check is enabled, but missing tgn_api info", "warning"
            )

        cls.testscript.parameters["script_args"][
            "tgn_ixia_viewid"
        ] = sste_common.ixia_getstatsurl(cls.test_data["tgn_api"])

        if not cls.testscript.parameters["script_args"]["tgn_ixia_viewid"]:
            return cls.failed(
                "Traffic check is enabled, but unable to get ixia traffic stats"
            )

        cls.log("Connected to traffic generator")
        return True

    @classmethod
    def check_system_NSR_state(cls):
        if sste_common.get_nsr_state(
            cls.testscript.parameters["script_args"], cls.testbed
        ):
            cls.log("Checked NSR state")
            return True
        else:
            return cls.failed("System failed NSR state check")

    @classmethod
    def verify_testbed_info_with_golden_snapshot(cls):
        if sste_common.check_testbed_snapshot(
            cls.testbed, cls.testscript.parameters["script_args"]
        ):
            cls.log("Verified testbed info with golden snapshop")
            return True

        else:
            return cls.failed("Cannot verify testbed info with golden snapshot")

    @classmethod
    def take_device_snapshot(cls):
        info = {}
        if (
            "snapshot_clis" in cls.test_data
            and cls.test_data["snapshot_clis"].strip() != ""
        ):
            info["clis"] = cls.test_data["snapshot_clis"].split(",")
        elif hasattr(
            cls.testbed.devices[
                cls.testscript.parameters["script_args"]["sste_device"]
            ].custom,
            "snapshot_clis",
        ):
            info["clis"] = cls.testbed.devices[
                cls.testscript.parameters["script_args"]["sste_device"]
            ].custom.snapshot_clis.split(",")
        if "snapshot_type" in cls.test_data:
            info["type"] = cls.test_data["snapshot_type"]
        elif hasattr(
            cls.testbed.devices[
                cls.testscript.parameters["script_args"]["sste_device"]
            ].custom,
            "snapshot_type",
        ):
            info["type"] = cls.testbed.devices[
                cls.testscript.parameters["script_args"]["sste_device"]
            ].custom.snapshot_type
        data = sste_common.get_snapshot_data(
            cls.testscript.parameters["script_args"], info
        )
        cls.testscript.parameters["snapshot"] = {"before": json.dumps(data, indent=2)}

        cls.log("Took device snapshot")
        return True

    @classmethod
    def get_ping_test_snapshot(cls):
        if (
            "ping_test_ip_list" not in cls.test_data
            or str(cls.test_data["ping_test_ip_list"]).strip() == ""
        ):
            return cls.skipped("Ping Test IP is not set")
        else:
            cls.testscript.parameters["script_args"]["ping_test_result"] = {}
            ips = cls.test_data["ping_test_ip_list"].split(",")
            for ip in ips:
                cls.testscript.parameters["script_args"]["ping_test_result"][
                    ip
                ] = sste_trigger.ping(
                    cls.testscript.parameters["script_args"], cls.testbed, ip
                )

        cls.log("Got ping test snapshot")
        return True

    @classmethod
    def backup_running_config_(
        cls, destination: str = "running_config_beforetrigger.txt"
    ):
        args = {
            "sste_commands": f"['show running-config | file harddisk:/{destination}']"
        }
        sste_common.exec_commands(args, cls.script_args)

        cls.log(f"Backed up running config to {destination}")
        return True

    @classmethod
    def backup_running_config(
        cls,
        destination: str = "running_config_beforetrigger.txt",
        target_router: str = None,
    ):
        return cls.run_on_router(target_router)(cls.backup_running_config_)(destination)

    @classmethod
    def restore_running_config_(cls, file="running_config_beforetrigger.txt"):
        config_data = {"file": file}
        cls.commit_replace(config_data)

        cls.log(f"Restored running config using {file}")
        return True

    @classmethod
    def restore_running_config(
        cls, file="running_config_beforetrigger.txt", target_router: str = None
    ):
        return cls.run_on_router(target_router)(cls.restore_running_config_)(file)

    @classmethod
    def backup_all_running_configs(cls, target_routers: list = None):
        target_needs_to_be_defined = target_routers is None
        if target_needs_to_be_defined:
            in_common_setup = cls.testcase is None
            if in_common_setup:
                target_routers = cls.testbed.devices.keys()
                target_routers = [
                    target_router
                    for target_router in target_routers
                    if not any(
                        target_router.startswith(blacklist_name)
                        for blacklist_name in ["cvt-auto", "special"]
                    )
                ]

            else:
                testcases = cls.test_data["testcase_data"]
                if cls.testcase in testcases.keys():
                    testcase_data = testcases[cls.testcase]
                    if "additional_routers_used" in testcase_data.keys():
                        target_routers = testcase_data["additional_routers_used"]
                    else:
                        target_routers = []

        target_routers = unique(target_routers)

        if target_routers:
            for target_router in target_routers:
                cls.backup_running_config(target_router=target_router)
        else:
            return cls.skipped("No additional routers to back up")

    @classmethod
    def set_test_parameters(cls):
        if "testsuite" in cls.test_data:
            cls.script_args["testsuitename"] = cls.test_data["testsuite"]
        if "testgroup" in cls.test_data:
            cls.script_args["testgroup"] = cls.test_data["testgroup"]
        cls.script_args["check_convergence_time"] = 1

        cls.log("Test parameters are set")
        return True

    @classmethod
    def get_testcases(cls, module_name: str) -> list:
        classes = inspect.getmembers(sys.modules[module_name], inspect.isclass)

        module_name_short = module_name.split(".")[-1]
        testcases = [
            (testcase_name, testcase_class)
            for (testcase_name, testcase_class) in classes
            if f"pyats.aetest.testscript.{module_name_short}." in str(testcase_class)
            and "Common" not in str(testcase_class)
        ]

        numbers = re.compile(r"(\d+)")
        testcases.sort(
            key=lambda name_class_pair: int(numbers.findall(name_class_pair[0])[-1])
        )
        return testcases

    @classmethod
    def skip_inactive_tests(cls, testcases: list):
        target_testcases = cls.test_data["active_testcases"]
        always_skipped_testcases = cls.test_data["always_skip_testcases"]
        target_testcases = [
            testcase
            for testcase in target_testcases
            if not testcase in always_skipped_testcases
        ]

        inactive_testcases = [
            testcase_class
            for (testcase_name, testcase_class) in testcases
            if testcase_name not in target_testcases
        ]

        for testcase_class in inactive_testcases:
            aetest.skip.affix(testcase_class, "skipped")
            print_(f"Skipping {testcase_class}")

    @classmethod
    def collect_node_list_from_device(cls):
        node_list = []
        cls.test_data["trigger_data"] = {}
        cls.test_data["testcases"] = []
        args = {
            "sste_commands": ["show platform | i R(S)*P"],
            "sste_delay": 30,
        }
        exclude_nodes = sste_common.exec_commands(
            args, cls.testscript.parameters["script_args"]
        )
        if "node_list" in cls.test_data:
            for node in cls.test_data["node_list"].split(","):
                if node not in exclude_nodes:
                    node_list.append(node)
            cls.test_data["node_list"] = node_list
        else:
            nodes_result = sste_common.show_platform(
                cls.testscript.parameters["script_args"]
            )
            for key, value in nodes_result.items():
                if key not in exclude_nodes and value["node_state"] in [
                    "OPERATIONAL",
                    "IOS XR RUN",
                ]:
                    node_list.append(key)
            cls.test_data["node_list"] = node_list
        count = 1
        if "count" in cls.test_data:
            count = int(cls.test_data["count"])
        for node in cls.test_data["node_list"]:
            if not node:
                continue
            else:
                for i in range(0, count):
                    testcase = "Reload Node: %s " % (node)
                    if i != 0:
                        testcase = testcase + "_" + str(i)
                    cls.test_data["testcases"].append(testcase)
                    cls.test_data["trigger_data"][testcase] = {
                        "node": node,
                        "iteration": i + 1,
                    }

        if not node:
            return cls.failed("Cannot collect nodes list")

        else:
            cls.log("Collected nodes list from device")
            return True

    @classmethod
    def take_platform_state(cls):
        info = ["admin show platform", "show platform"]
        if cls.testscript.parameters["script_args"]["os_type"] in ["8000"]:
            info = ["show platform"]
        cls.testscript.parameters["script_args"][
            "platform_before"
        ] = sste_common._get_snapshot_data(
            cls.testscript.parameters["script_args"], info
        )

        cls.log("Took platform state")
        return True

    @classmethod
    def full_textfsm_path(cls, filename: str):
        return cls.test_data["textfsm_folder"] + filename

    @classmethod
    def testcase_overview(cls, testcase_name):
        if testcase_name in cls.test_data["testcase_data"]:
            testcase_data = cls.test_data["testcase_data"][testcase_name]
            if "overview" in testcase_data.keys():
                overview_data = testcase_data["overview"]

                if "title" in overview_data.keys():
                    title = overview_data["title"]
                    cls.log(f"Purpose: {title}")

                if "procedure" in overview_data.keys():
                    procedure = overview_data["procedure"]
                    if procedure:
                        if isinstance(procedure, list):
                            if len(procedure) > 1:
                                cls.log("Procedure:")
                                for i, procedure_step in enumerate(procedure, start=1):
                                    cls.log(f"{i})  {procedure_step}")
                            else:
                                procedure = procedure[0]
                                cls.log(f"Procedure: {str(procedure)}")
                        else:
                            cls.log(f"Procedure: {str(procedure)}")

                if "topology" in overview_data.keys():
                    topology = overview_data["topology"]
                    if topology:
                        if isinstance(topology, list):
                            if len(topology) > 1:
                                cls.log("Topology:")
                                for traffic in topology:
                                    cls.log(traffic)
                            else:
                                topology = topology[0]
                                cls.log(f"Topology: {str(topology)}")
                        else:
                            cls.log(f"Topology: {str(topology)}")

            else:
                cls.skipped("Overview of test plan is unavailable")

        else:
            cls.skipped("This testcase has no specified data")

    @classmethod
    def verify_version_meets_minimum_requirement(cls, minimum_version="0.0.0"):
        parsed_output = cls.run_cmds("show version", "show_version.textfsm")
        module_args = {"sste_commands": ["show version"]}

        actual_version = parsed_output["Version"]

        part_parser = re.compile(r"(\d+)\w*")

        target_version_details = minimum_version.split(".")
        target_version_details = [
            int(part_parser.findall(target_part)[0])
            for target_part in target_version_details
        ]

        actual_version_details = actual_version.split(".")
        actual_version_details = [
            int(part_parser.findall(actual_part)[0])
            for actual_part in actual_version_details
        ]

        for actual_part, target_part in zip(
            actual_version_details, target_version_details
        ):
            if actual_part > target_part:
                cls.log(f"Version {actual_version} is at least {minimum_version}")
                return True

            elif actual_part < target_part:
                return cls.failed(
                    f"Version {actual_version} is older than {minimum_version}"
                )

        if len(actual_version_details) >= len(target_version_details):
            cls.log(f"Version {actual_version} is at least {minimum_version}")
            return True

        else:
            return cls.failed(
                f"Version {actual_version} is older than {minimum_version}"
            )

    @classmethod
    def find_rpm(cls, parsed_rpm_dictionary, packet_name) -> bool:
        for category in parsed_rpm_dictionary["Category"].keys():
            existing_packets = parsed_rpm_dictionary["Category"][category][
                "Packet"
            ].keys()
            if packet_name in existing_packets:
                cls.log(f"Found RPM {packet_name}")
                return True
        return False

    @classmethod
    def check_rpm(cls, target_rpm=[]):
        parsed_output = cls.run_cmds(
            "show install active summary", "show_install_active_summary_v2.textfsm"
        )

        if target_rpm:
            rpm_status = []
            for target in target_rpm:
                target_exists = cls.find_rpm(parsed_output, target)
                rpm_status.append(target_exists)

            missing_rpm = [
                target_rpm[i]
                for i, rpm_exists in enumerate(rpm_status)
                if not rpm_exists
            ]

            if missing_rpm:
                return cls.failed(f"Missing RPM: {', '.join(missing_rpm)}")
            else:
                cls.log("All target RPMs exist")
                return True

        else:
            for category in parsed_output["Category"].keys():
                existing_packets = parsed_output["Category"][category]["Packet"].keys()
                if existing_packets:
                    cls.log("RPM exists")
                    return True

            return cls.failed("No RPM on router")

    @classmethod
    def _format(cls, line, replacewith: dict = None):
        """
        For a given line, if {some_key} exists, run string.format(**replacewith).
        if replacewith is None, it is assumed to be cls.test_data
        """
        needs_replacing = re.findall("{\w+}", line)
        if needs_replacing:
            if replacewith is None:
                replacewith = cls.test_data
            try:
                line = line.format(**replacewith)
            except KeyError as e:
                fail_message = (
                    f"{type(e).__name__} when formatting {line}: {', '.join(e.args)}"
                )
                cls.log(fail_message, "warning")
        return line

    @classmethod
    def get_setting(cls, config_data: dict):
        """
        For a given config_data dictionary, generate texts that describe what it is for based on "purpose" and "router".
        """
        setting = config_data["purpose"] if "purpose" in config_data.keys() else ""
        setting = f" to {setting[0].lower()}{setting[1:]}" if setting else ""
        setting = (
            f" on {config_data['router']}" + setting
            if "router" in config_data.keys()
            else setting
        )
        setting = cls._format(setting)
        return setting

    @classmethod
    def copy_to_router(cls, config_data: dict):
        """
        config_data must have "path" and "file", which refer to a file on the local server.
        optionally, "path" can be unspecified and included in "file".
        config_data may also have "router", which refers to the router it is copying the file to.
        if "router" is not in config_data, it is inferred that the target router is the test script's original router.
        Note that "router" is used for logging only here. Ssh'ing into the router is done separately using switch_router() and is not included in this function.
        """
        username = cls.test_data["config_server_login"]
        password = cls.test_data["config_server_password"]
        ip = cls.test_data["config_server"]

        if "path" in config_data.keys():
            filepath = config_data["path"]
            filename = config_data["file"]
        else:
            path_in_filename = config_data["file"].rfind("/") >= 0
            if path_in_filename:
                filepath = config_data["file"][: config_data["file"].rfind("/")]
                filename = config_data["file"].split("/")[-1]
            else:
                filepath = ""
                filename = config_data["file"]

        filepath = cls._format(filepath)
        filename = cls._format(filename)

        vrf = cls.test_data["mgmt_vrf"]

        full_path = f"{username}@{ip}:{filepath}/{filename}"
        scp_instructions = {
            "cmd": f"scp {full_path} /harddisk: vrf {vrf}",
            "password": password,
        }
        copy_successful = sste_common.scp(
            cls.script_args, cls.testbed, scp_instructions
        )

        if copy_successful:
            args = {"sste_commands": f"['run chmod 777 /harddisk:/{filename}']"}
            sste_common.exec_commands(args, cls.script_args)

            module_args = {"sste_commands": f"['dir harddisk:/{filename}']"}
            output = sste_common.exec_commands(module_args, cls.script_args)

            copied_file_exists = not (
                output.replace("\n", "").find("Path does not exist") > 0
                or output.replace("\n", "").find("No such file or directory") > 0
            )
            if copied_file_exists:
                cls.log(f"Copied {filename}{cls.get_setting(config_data)}")
                return True
            else:
                cls.failed(f"Unable to copy config{cls.get_setting(config_data)}")

        else:
            cls.failed(f"Unable to copy config{cls.get_setting(config_data)}")

    @classmethod
    def commit_replace(cls, config_data: dict):
        """
        config_data must have "file", which refers to an existing file on harddisk:/
        otherwise, commit-replace is skipped
        """
        filename = config_data["file"].split("/")[-1]
        filename = cls._format(filename)

        related_files_in_harddisk = cls.run_cmds(f"run ls /harddisk: | grep {filename}")
        file_exists = filename in related_files_in_harddisk.splitlines()

        if file_exists:
            print_(f"Found harddisk:{filename}")

            label = "cvt-auto_" + str(int(time()))
            args = {
                "sste_commands": [
                    f"load harddisk:/{filename}",
                    f"commit replace label {label}",
                ],
                "timeout": 1800,
            }

            output = sste_common.safe_config_commands(args, cls.script_args)

            if output:
                if "Failed to commit one or more configuration items" in output:
                    return cls.failed(
                        f"Cannot commit-replace using harddisk:/{filename}{cls.get_setting(config_data)}"
                    )

                cls.log(
                    f"Finished commit-replace using harddisk:/{filename}{cls.get_setting(config_data)}"
                )
                cls.script_args["need_to_reload_lcs"] = (
                    "you must manually reload" in output
                )
                return True
            else:
                return cls.failed(
                    f"Cannot commit-replace using harddisk:/{filename}{cls.get_setting(config_data)}"
                )

        else:
            cls.skipped(f"Cannot find harddisk:{filename}")

    @classmethod
    def configure(cls, config_data: dict):
        """
        Applies a given set of config instructions using either "conf t" or commit replace. Rolls back the config if rollback is True.
        if config_data is a string, it is assumed to be the only config.
        if config_data is a list, it is assumed to be a list of configs.
        otherwise, config_data is a dictionary that can have "purpose", "router", "path", "file", and "cmds"

        conf t using config_data["cmds"]
        """
        if isinstance(config_data, str):
            config_data = [config_data]
        if isinstance(config_data, list):
            config_data = {"cmds": config_data}

        config_data["cmds"] = [cls._format(cmd) for cmd in config_data["cmds"]]

        configs = config_data["cmds"]
        args = {
            "sste_commands": configs,
            "timeout": 1800,
        }

        output = sste_common.safe_config_commands(args, cls.script_args)

        if output:
            cls.log(f"Finished applying configs{cls.get_setting(config_data)}")
            return True
        else:
            cls.failed(f"Cannot apply configs{cls.get_setting(config_data)}")

    @classmethod
    def rollback_configs(cls, config_data: Union[str, list, dict, int]):
        """
        If config_data is an int, it is assumed to be the number of rollbacks needed:
        Otherwise, the number of rollbacks needed is inferred based on config_data:
        If config_data is a string or a list of strings, it is assumed that it is a list of config commands applied all at once.
        Therefore, the number of rollbacks is 1.
        If it is a dictionary, the number of rollbacks can be 0, 1, or 2:
        Starting with 0 rollbacks,
        If "file" is in the dictionary, it is assumed that a commit-replace is applied.
        Therefore, the number of rollbacks +1.
        if "cmds" is in the dictionary, it is assumed that a list of config commands is applied all at once.
        Therefore, the number of rollbacks +1.
        """
        num_rollbacks = 0
        if isinstance(config_data, int):
            num_rollbacks = config_data

        else:
            if isinstance(config_data, str):
                config_data = [config_data]
            if isinstance(config_data, list):
                config_data = {"cmds": config_data}

            commit_replace_mode = "file" in config_data.keys()
            if commit_replace_mode:
                num_rollbacks += 1

            conf_t_mode = "cmds" in config_data.keys()
            if conf_t_mode:
                num_rollbacks += 1

        if num_rollbacks:
            module_args = {
                "sste_commands": [
                    f"show configuration commit changes last {num_rollbacks}",
                    f"rollback configuration last {num_rollbacks}",
                ],
            }
            rollback_successful = sste_common.exec_commands(
                module_args, cls.script_args
            )

            if rollback_successful:
                cls.log(f"Rolled back {num_rollbacks} configs")
                cls.script_args["need_to_reload_lcs"] = True
                return True

            else:
                cls.failed(f"Cannot roll back {num_rollbacks} configs")

        else:
            cls.log("Nothing to roll back")
            return True

    @classmethod
    def rollback_config_on_device(cls, device_name: str, rollbacks_needed: int = 1):
        cls.run_on_router(device_name)(cls.rollback_configs)(rollbacks_needed)

    @classmethod
    def apply_configs_(
        cls, config_data: Union[str, list, dict], rollback=False, replacewith=None
    ):
        """
        Applies a given set of config instructions using either "conf t" or commit replace. Rolls back the config if rollback is True.
        if config_data is a string, it is assumed to be the only config.
        if config_data is a list, it is assumed to be a list of configs.
        otherwise, config_data is a dictionary that can have "purpose", "router", "path", "file", and "cmds"
        "router" is used in apply_configs().
        if "file" is in config_data, use commit replace.
        if "path" is in config_data or "file" has "/" (meaning a file path is included), scp the file from the local server to the router first.
        if "cmds" is in config_data, apply cmds after commit-replace, if commit-replace took place, or just apply cmds. Note that cmds is a list of strings.
        if rollback, execute "rollback configuration last X" after applying the config. X = commit-replace? (0 or 1) + conf-t? (0-1).
        config_data can also have a "purpose" that is logged as an explanation for the config.
        """
        if isinstance(config_data, str):
            config_data = [config_data]
        if isinstance(config_data, list):
            config_data = {"cmds": config_data}

        clock = cls.run_cmds("show clock", log_output=False)
        cls.script_args["log_start_time"] = sste_common.parse_clock(clock)

        commit_replace_mode = "file" in config_data.keys()
        scp_first = "path" in config_data.keys() or (
            commit_replace_mode and config_data["file"].find("/") > -1
        )
        conf_t_mode = "cmds" in config_data.keys()

        if commit_replace_mode:
            if scp_first:
                cls.copy_to_router(config_data)
            cls.commit_replace(config_data)

        if conf_t_mode:
            cls.configure(config_data)

        if rollback:
            cls.rollback_configs(config_data)

        return True

    @classmethod
    def apply_configs(
        cls, config_data: Union[str, list, dict], rollback=False, replacewith=None
    ):
        """
        Applies a given set of config instructions using either "conf t" or commit replace. Rolls back the config if rollback is True.
        if config_data is a string, it is assumed to be the only config.
        if config_data is a list, it is assumed to be a list of configs.
        otherwise, config_data is a dictionary that can have "purpose", "router", "path", "file", and "cmds"
        if "router" is in config_data, ssh into the router first. Note that config_data["router"] is a string that must match a router name on Area51.
        if "file" is in config_data, use commit replace.
        if "path" is in config_data or "file" has "/" (meaning a file path is included), scp the file from the local server to the router first.
        if "cmds" is in config_data, apply cmds after commit-replace, if commit-replace took place, or just apply cmds. Note that cmds is a list of strings.
        if rollback, execute "rollback configuration last X" after applying the config. X = commit-replace? (0 or 1) + conf-t? (0-1).
        config_data can also have a "purpose" that is logged as an explanation for the config.
        """
        if isinstance(config_data, str):
            config_data = [config_data]
        if isinstance(config_data, list):
            config_data = {"cmds": config_data}

        router = (
            config_data["router"]
            if (
                "router" in config_data.keys()
                and config_data["router"] != cls.test_data["UUT"]
            )
            else None
        )

        if router is None:
            return cls.apply_configs_(config_data, rollback, replacewith)

        else:
            return cls.run_on_router(router)(cls.apply_configs_)(
                config_data, rollback, replacewith
            )

    @classmethod
    def apply_testcase_configs(cls, config_num: int, rollback=False):
        """
        For the current testcase, fetch and apply the yaml config with the given config_num. Rollback if rollback is True.
        """
        testcase_configs = cls.test_data["testcase_data"][cls.testcase]["configs"]
        config_data = testcase_configs[config_num]
        cls.apply_configs(config_data, rollback)

    @classmethod
    def apply_golden_configs_(cls, target_router: str = None):
        """
        Searches test_data for information on the golden config file for the target router.
        Does not ssh into the target router.
        If target_router is None, it is assumed to be the original router.
        """
        if target_router is None:
            if "initial_uut" in cls.test_data.keys():
                target_router = cls.test_data["initial_uut"]
            else:
                target_router = cls.test_data["UUT"]

        if (
            "golden_configs" in cls.test_data.keys()
            and target_router in cls.test_data["golden_configs"].keys()
        ):
            config_data = cls.test_data["golden_configs"][target_router]

            cls.apply_configs(config_data)

            cls.log(f"Applied golden configs to {target_router}")
            return True

        else:
            return cls.skipped(f"No golden router configs to apply to {target_router}")

    @classmethod
    def apply_golden_configs(cls, target_router: str = None):
        if target_router is None:
            if "initial_uut" in cls.test_data.keys():
                target_router = cls.test_data["initial_uut"]
            else:
                target_router = cls.test_data["UUT"]

        cls.run_on_router(target_router)(cls.apply_golden_configs_)(target_router)

    @classmethod
    def apply_all_golden_configs(cls, target_routers: list = None):
        target_needs_to_be_defined = target_routers is None
        if target_needs_to_be_defined:
            in_common_setup = cls.testcase is None
            if in_common_setup:
                target_routers = cls.testbed.devices.keys()
                target_routers = [
                    target_router
                    for target_router in target_routers
                    if not any(
                        target_router.startswith(blacklist_name)
                        for blacklist_name in ["cvt-auto", "special"]
                    )
                ]

            else:
                target_routers = [cls.test_data["initial_uut"]]
                testcases = cls.test_data["testcase_data"]
                if cls.testcase in testcases.keys():
                    testcase_data = testcases[cls.testcase]
                    if "additional_routers_used" in testcase_data.keys():
                        target_routers = (
                            target_routers + testcase_data["additional_routers_used"]
                        )

        target_routers = unique(target_routers)

        for router in target_routers:
            cls.apply_golden_configs(router)

    @classmethod
    def remove_configs(cls, configs: Union[str, list, dict]):
        """
        To be implemented
        """
        if isinstance(configs, str):
            configs = [configs]
        if isinstance(configs, list):
            for config in configs:
                if "\n" in config:
                    config_parts = config.splitlines()

    @classmethod
    def get_formal_configs(cls, include: list = [], exclude: list = []) -> list:
        """
        Gets the formal config as a list of configs.
        """
        if isinstance(include, str):
            include = [include]
        if isinstance(exclude, str):
            exclude = [exclude]
        include = [f"include {line}" for line in include]
        exclude = [f"exclude {line}" for line in exclude]
        cmd = ["show run formal"] + include + exclude
        cmd = " | ".join(cmd)
        output = cls.run_cmds(cmd)

        parsed_configs = cls.parse_formal_configs(output)
        return parsed_configs

    @classmethod
    def cleanup_configs(cls):
        """
        For the current testcase, fetch all yaml configs where the config number is negative.
        Apply them all in the order of lowest (most negative) to biggest (most positive, usually -1).
        """
        testcase_configs = cls.test_data["testcase_data"][cls.testcase]["configs"]

        cleanup_config_nums = [
            config_num for config_num in testcase_configs.keys() if config_num < 0
        ]
        cleanup_config_nums.sort()

        for config_num in cleanup_config_nums:
            config_data = testcase_configs[config_num]
            cls.apply_configs(config_data)

    @classmethod
    def string_to_list_of_single_layer_textfsm_dictionary(
        cls, cli_output, textfsm_file
    ):
        from textfsm import TextFSM

        try:
            template = open(textfsm_file, "r")
            fsm = TextFSM(template)
            headers = list(fsm.header)
            data_points = fsm.ParseText(cli_output)

        except Exception as e:
            print_(headers)
            print_(data_points)
            cls.log("Failed to parse cli output using textfsm.", "warning")
            cls.log("{}.".format(str(e)), "warning")
            return []

        parsed_output = [
            {header: value for header, value in zip(headers, data_point)}
            for data_point in data_points
        ]

        return parsed_output

    @classmethod
    def parse_with_textfsm(
        cls, cli_output: str, textfsm_file: str, simple_output: bool = False
    ):
        if not textfsm_file.startswith(cls.test_data["textfsm_folder"]):
            textfsm_file = cls.full_textfsm_path(textfsm_file)

        if simple_output:
            parsed_output = cls.string_to_list_of_single_layer_textfsm_dictionary(
                cli_output, textfsm_file
            )
        else:
            parsed_output = sste_common.string_to_textfsm_dict(
                cls.script_args, cli_output, textfsm_file
            )

        return parsed_output

    @classmethod
    def check_cli_output_for_errors(cls, cmds, raw_output):
        """
        Checks a cli output for error messages using the cmd_prefix_and_error_messages_and_troubleshoot_categories dictionary.
        If an error is found, update cls.troubleshoot_categories and enable the "failed" troubleshoot level.
        Return True if an error is found. Else, return False.
        """
        cmd_prefix_and_error_messages_and_troubleshoot_categories = {
            "*": {},
            "show lldp neighbor": {
                "'sysdb' detected the 'warning' condition": [
                    "sysdb",
                ],
                "took too long to process a request": [],
            },
        }

        if isinstance(cmds, str):
            cmds = [cmds]

        error_found = False
        for (
            cmd_prefix,
            error_details,
        ) in cmd_prefix_and_error_messages_and_troubleshoot_categories.items():
            prefix_matched = cmd_prefix == "*" or any(
                cmd.startswith(cmd_prefix) for cmd in cmds
            )
            if prefix_matched:
                for error_message, troubleshoot_categories in error_details.items():
                    if error_message in raw_output:
                        cls.update_troubleshooting_categories(troubleshoot_categories)
                        cls.testcase_passed = False
                        error_found = True

        return error_found

    @classmethod
    def run_cmds(
        cls,
        cmds: Union[str, list] = None,
        textfsm_files: Union[str, list] = None,
        replacewith: dict = None,
        simple_output: bool = False,
        check_for_errors: bool = True,
        retries: int = 1,
        log_output: bool = True,
    ):
        """
        run the given cmds.
        Replace {} in any cmd by referencing replacewith dictionary.
        if replacewith is None, refer to cls.test_data.
        Optionally, parse the output using textfsm_file.
        If simple_output is True, parsing output with textfsm returns a list of single-layer dictionaries.
        Reruns the cmd for a maximum of <retries> times. Rerun if it hits an error.

        Parameters
        ----------
        cmds: Union[str, list]
            One cli command, or a list of cli commands.
            May include {<keywords>}, which can be looked up using replacewith

        textfsm_files: Union[str, list] (Default: None)
            The names of textfsm files.
            If None is given, return the raw cmd output.
            If one is given, whether in a string or a list of 1 item, apply it to all cmds.
            If a multi-item list is given, attempt to pair each textfsm with one cmd, and discard any unpaired one (any unpaired cmd will still be run, but their outputs will be dropped).

        replacewith: dict (Default: None)
            A dictionary from which to replace parts of the cmds.
            If None is given, skip this step.

        simple_output: bool (Default: True)
            If True, for each cmd, return a single-layer list of single-layer dictionaries using TextFSM.ParseText().
            If False, for each cmd, merge the single-layer list of dictionaries into a multi-layer dictionary using sste_common.string_to_textfsm_dic().
            Only applies if textfsm file is not None.

        check_for_errors: bool (Default: True)
            If True, check for error messages in each cmd's output. If an error is found, update troubleshooting categories and attempt to rerun the cmd.

        retries: int (Default: 1)
            The number of reruns allowed if check_for_errors is True.

        log_output: bool (Default: True)
            The "log_output" parameter in sste_common.exec_commands()'s args argument.

        Output
        ------
        List in, list out.
        If a list of commands is given, return a list of outputs, one for each command.
        If a string is given, return the output (either raw, as a string, or parsed).
        """
        cmds_is_string = isinstance(cmds, str)
        cmds = [cmds] if cmds_is_string else cmds

        cmds = [cls._format(cmd, replacewith) for cmd in cmds]

        cls.script_args["trigger_start_time"] = time()

        need_to_rerun = False
        for i in range(retries):
            outputs = [
                sste_common.exec_commands(
                    {"sste_commands": [cmd], "log_output": log_output}, cls.script_args
                )
                for cmd in cmds
            ]

            if check_for_errors:
                errors = [
                    cls.check_cli_output_for_errors(cmd, output)
                    for cmd, output in zip(cmds, outputs)
                ]
                need_to_rerun = any(error for error in errors)

            if need_to_rerun:
                if i < retries - 1:
                    cls.log(f"Error detected during attempt {i+1}. Retrying", "warning")
                else:
                    cls.log(
                        f"Error detected. Max attempt ({retries}) reached. Proceeding",
                        "warning",
                    )
            else:
                break

        if textfsm_files is not None and textfsm_files:
            if isinstance(textfsm_files, list) and len(textfsm_files) == 1:
                textfsm_files = textfsm_files[0]
            if isinstance(textfsm_files, str):
                outputs = [
                    cls.parse_with_textfsm(
                        output, textfsm_files, simple_output=simple_output
                    )
                    for output in outputs
                ]
            else:
                outputs = [
                    cls.parse_with_textfsm(output, file, simple_output=simple_output)
                    for output, file in zip(outputs, textfsm_files)
                ]

        if cmds_is_string:
            outputs = outputs[0]

        return outputs

    @classmethod
    def clear_syslog(cls):
        cls.run_cmds("clear logging")

    @classmethod
    def identify_ixia_traffic(cls, base_url=""):
        base_url = base_url if base_url else cls.test_data["tgn_api"]
        sste_tgn.ixia_get_traffic_items(cls.script_args, cls.test_data["tgn_api"])

        cls.log(f"identified traffic: {cls.script_args['ixia_streamlist']}")
        return True

    @classmethod
    def disable_all_ixia_traffic(cls):
        if "ixia_streamlist" not in cls.script_args:
            cls.script_args["ixia_streamlist"] = {}

        ixia_url = cls.test_data["tgn_api"]
        streams = cls.script_args["ixia_streamlist"]

        disabled_all = True
        for stream in streams:
            stream_disabled = sste_tgn.ixia_disable_traffic_item(
                cls.script_args, ixia_url, stream
            )
            if stream_disabled:
                cls.log("Disabled traffic item: " + stream)
            else:
                cls.log("Failed to disable traffic item: " + stream, "warning")
                disabled_all = False

        sste_tgn.ixia_apply_traffic_items(cls.script_args, ixia_url)

        if disabled_all:
            cls.log("Disabled all traffic items")
            return True
        else:
            return cls.failed("Failed to disable all traffic items")

    @classmethod
    def start_ixia_traffic(
        cls, traffic_num: int, enable_first: bool = True, max_apply_attempts: int = 3
    ):
        testcase_data = cls.test_data["testcase_data"][cls.testcase]
        streams = testcase_data["traffic"][f"group{traffic_num}"]
        if isinstance(streams, str):
            streams = [streams]

        if streams:
            sste_tgn.tgn_connect(
                cls.script_args, cls.testbed, cls.test_data["tgn"], cls.test_data
            )
            cls.log("Connected to tgn")

            enabled_streams = not enable_first or cls.enable_ixia_traffic(
                traffic_num=traffic_num, max_apply_attempts=max_apply_attempts
            )

            # if enabled_streams:
            traffic_started = sste_tgn.tgn_start_traffic(
                cls.script_args, cls.test_data["tgn"], streams
            )

            if traffic_started:
                cls.log(f"Started traffic streams {', '.join(streams)}")
                return True
            else:
                return cls.failed(f"Cannot start traffic streams {', '.join(streams)}")

    @classmethod
    def stop_ixia_traffic(cls, traffic_num: int = None):
        if traffic_num is None:
            streams = None
        else:
            testcase_data = cls.test_data["testcase_data"][cls.testcase]
            streams = testcase_data["traffic"][f"group{traffic_num}"]

        if streams is None or streams:
            sste_tgn.tgn_connect(
                cls.script_args, cls.testbed, cls.test_data["tgn"], cls.test_data
            )
            cls.log("Connected to tgn")

            traffic_stopped = sste_tgn.tgn_stop_traffic(
                cls.script_args, cls.test_data["tgn"], streams
            )

            if traffic_stopped:
                if streams:
                    cls.log(f"Stopped traffic streams {', '.join(streams)}")
                else:
                    cls.log("Stopped all traffic streams")
                return True
            else:
                return cls.failed(f"Cannot stop traffic streams {', '.join(streams)}")

    @classmethod
    def enable_ixia_traffic(cls, traffic_num: int, max_apply_attempts: int = 3):
        """
        Through REST API, enables the specified traffic items on IXIA VM, then apply it.
        """
        testcase_data = cls.test_data["testcase_data"][cls.testcase]
        streams = testcase_data["traffic"][f"group{traffic_num}"]
        if isinstance(streams, str):
            streams = [streams]

        for stream in streams:
            if sste_tgn.ixia_enable_traffic_item(
                cls.script_args, cls.test_data["tgn_api"], stream
            ):
                cls.log("Traffic item: " + stream + " is enabled.")
            else:
                return cls.failed("Cannot enable traffic item: " + stream)

        traffic_applied = False
        for i in range(max_apply_attempts):
            traffic_applied = sste_tgn.ixia_apply_traffic_items(
                cls.script_args, cls.test_data["tgn_api"]
            )
            if traffic_applied:
                break
            else:
                print(
                    f"Attempt to apply traffic items failed {i+1} time{'s' if i else ''}"
                )
                cls.wait(5)
        if traffic_applied:
            print_("Applied traffic items")
        else:
            print_("Cannot apply traffic. There may be no change to apply. Proceeding.")

        cls.log(f"Enabled traffic streams {', '.join(streams)}")
        return True

    @classmethod
    def disable_ixia_traffic(cls, traffic_num: int = None):
        if traffic_num is None:
            streams = [None]
        else:
            testcase_data = cls.test_data["testcase_data"][cls.testcase]
            streams = testcase_data["traffic"][f"group{traffic_num}"]

        for stream in streams:
            if sste_tgn.ixia_disable_traffic_item(
                cls.script_args, cls.test_data["tgn_api"], stream
            ):
                cls.log("Traffic item: " + stream + " is disabled.")
            else:
                return cls.failed("Failed to disable traffic item: " + stream)

        sste_tgn.ixia_apply_traffic_items(cls.script_args, cls.test_data["tgn_api"])
        cls.log(f"Disabled traffic streams {', '.join(streams)}")
        return True

    @classmethod
    def get_ixia_stats_with_unknown_traffic_items(
        cls, interested_fields: Union[str, list] = "Loss %"
    ):
        """
        Identifies all running traffic, pauses them temporarily to acquire their stats, then restarts them.
        If no running traffic is present, acquire all existing stats.
        """
        if interested_fields is not None and isinstance(interested_fields, str):
            interested_fields = [interested_fields]

        baseline_ixia_stats = sste_tgn.tgn_get_stats_flexible(
            cls.script_args, cls.test_data["tgn"], print_output=False
        )
        sleep(1)  # TODO determine if 1 sec is enough
        new_ixia_stats = sste_tgn.tgn_get_stats_flexible(
            cls.script_args, cls.test_data["tgn"], print_output=False
        )

        running_traffic_names = [
            traffic_name
            for traffic_name in baseline_ixia_stats.keys()
            if traffic_name in new_ixia_stats.keys()
            and any(
                baseline_ixia_stats[traffic_name][field]
                != new_ixia_stats[traffic_name][field]
                for field in baseline_ixia_stats[traffic_name].keys()
                if field in new_ixia_stats[traffic_name].keys()
            )
        ]

        if running_traffic_names:
            sste_tgn.tgn_connect(
                cls.script_args, cls.testbed, cls.test_data["tgn"], cls.test_data
            )
            sste_tgn.tgn_stop_traffic(
                cls.script_args, cls.test_data["tgn"], running_traffic_names
            )
            sleep(1)  # TODO determine if 1 sec is enough

        ixia_stats = sste_tgn.tgn_get_stats_flexible(
            cls.script_args,
            cls.test_data["tgn"],
            streams=running_traffic_names,
            interested_fields=interested_fields,
            print_output=False,
        )

        if running_traffic_names:
            sste_tgn.ixia_enable_traffic_item(
                cls.script_args, cls.test_data["tgn_api"], running_traffic_names
            )
            sste_tgn.ixia_apply_traffic_items(cls.script_args, cls.test_data["tgn_api"])
            sste_tgn.tgn_start_traffic(
                cls.script_args, cls.test_data["tgn"], running_traffic_names
            )

        return ixia_stats

    @classmethod
    def sanity_traffic_check(cls, ixia_goal: str = "show"):
        ixia_stats = cls.get_ixia_stats_with_unknown_traffic_items()
        print_(ixia_stats)

        if ixia_goal == "show":
            return True

        elif ixia_goal == "lossless":
            for stream, stats in ixia_stats.items():
                if stats["Loss %"] > 0:
                    cls.failed(f"Loss detected in {stream}")

        elif ixia_goal == "lossy":
            for stream, stats in ixia_stats.items():
                if stats["Loss %"] == 0:
                    cls.failed(f"No loss detected in {stream}")

    @classmethod
    def get_ixia_stats(
        cls,
        traffic: Union[int, str, list] = None,
        interested_fields: Union[str, list] = None,
    ):
        """
        If traffic is None, get all ixia stats
        If traffic is an integer, assume it is a testcase traffic group number
        If traffic is a string, assume it is a traffic stream name
        If traffic is a list, assume it is a list of traffic stream names
        """
        if isinstance(traffic, int):
            try:
                testcase_data = cls.test_data["testcase_data"][cls.testcase]
                traffic = testcase_data["traffic"][f"group{traffic}"]
            except KeyError as e:
                cls.log(
                    f"Cannot acquire traffic items in group {traffic}. Acquiring all traffic stats instead.",
                    "warning",
                )
                traffic = None
        elif isinstance(traffic, str):
            traffic = [traffic]

        if interested_fields is not None and isinstance(interested_fields, str):
            interested_fields = [interested_fields]

        all_ixia_stats = sste_tgn.tgn_get_stats_flexible(
            cls.script_args, cls.test_data["tgn"], traffic, interested_fields
        )

        # cls.log(f"Acquired IXIA statistics: {all_ixia_stats}")
        return all_ixia_stats

    @classmethod
    def ensure_ixia_stats_no_loss(cls, traffic_num: int = 1):
        cls.stop_ixia_traffic(traffic_num)
        cls.wait(10)

        stats = cls.get_ixia_stats(traffic_num, ["Loss %"])

        cls.start_ixia_traffic(traffic_num)

        lossy_traffic = {
            traffic_name: traffic_stats["Loss %"]
            for traffic_name, traffic_stats in stats.items()
            if traffic_stats["Loss %"] > 0
        }

        if lossy_traffic:
            loss_log = [
                f"{traffic_name}'s loss % is {traffic_stats['Loss %']}"
                for traffic_name, traffic_stats in stats.items()
            ]
            return cls.failed(", ".join(loss_log))

        else:
            cls.log(f"{', '.join(stats.keys())}'s loss % are all 0")

    @classmethod
    def clear_ixia_stats(cls, traffic_num: int):
        testcase_data = cls.test_data["testcase_data"][cls.testcase]
        streams = testcase_data["traffic"][f"group{traffic_num}"]

        sste_tgn.tgn_clear_stats(cls.script_args, cls.test_data["tgn"], streams)
        cls.log(f"Cleared IXIA stats for traffic streams {', '.join(streams)}")

    @classmethod
    def ensure_ixia_is_running(cls, traffic_num: int = None):
        cls.stop_ixia_traffic(traffic_num)

        cls.wait(10)

        ixia_stats = cls.get_ixia_stats(
            traffic_num, ["Rx Frames", "Tx Frames", "Loss %"]
        )

        try:
            testcase_data = cls.test_data["testcase_data"][cls.testcase]
            streams = testcase_data["traffic"][f"group{traffic_num}"]
        except KeyError as e:
            streams = list(ixia_stats.keys())

        traffic_missing = [
            stream for stream in streams if stream not in ixia_stats.keys()
        ]
        if traffic_missing:
            cls.passx(f"Cannot find traffic stats for {', '.join(traffic_missing)}")

        tx_not_increasing = [
            stream for stream in streams if ixia_stats[stream]["Tx Frames"] == 0
        ]
        if tx_not_increasing:
            cls.skipped(
                f"Traffic items not sending traffic: {', '.join(tx_not_increasing)}"
            )

        rx_not_increasing = [
            stream for stream in streams if ixia_stats[stream]["Rx Frames"] == 0
        ]
        if rx_not_increasing:
            cls.passx(
                f"Traffic items not receiving traffic: {', '.join(rx_not_increasing)}"
            )

        cls.start_ixia_traffic(traffic_num)

    @classmethod
    def send_webex_summary(cls, testcase):
        if not cls.test_data["webex_notification"] == "none":
            message = "Testcase " + cls.testcase + " is " + str(testcase.result)
            print_(message)
            webex_id = sste_common._get_webexteam_id(cls.testbed)
            sste_common.send_webex_team(message, webex_id)

    @classmethod
    def disconnect(cls):
        if cls.testbed.devices:
            for host, connection in cls.testbed.devices.items():
                if connection:
                    connection.disconnect()
                    cls.log(f"Disconnected from {host}")

    @classmethod
    def display_timing_report(cls):
        table = Texttable()
        if "timing" in cls.script_args and cls.script_args["timing"]:
            cls.timing.update(cls.script_args["timing"])
        if cls.timing:
            cls.log("Trigger Timing Report")
            for config, val in cls.timing.items():
                table.add_rows([["Trigger", "time"], [config, val]])
            cls.log(table.draw())

    @classmethod
    def upload_log(cls):
        sste_common.upload_log(cls.script_args, cls.testbed, cls.test_data)

    @classmethod
    def parse_formal_configs(cls, show_run_formal_output: str):
        configs, current_config = [], []

        lines = show_run_formal_output.splitlines()
        lines = [line.rstrip() for line in lines if line.strip()]

        for line in lines:
            if line.startswith("Building configuration"):
                configs, current_config = [], []
            elif line.lstrip().startswith("!"):
                continue
            elif line[0] != line.lstrip()[0]:
                current_config.append(line)
            elif line.rstrip()[-1] == "#":
                if current_config:
                    configs.append("\n".join(current_config))
                    current_config = []
                break
            else:
                if current_config:
                    configs.append("\n".join(current_config))
                current_config = [line]

        if current_config:
            configs.append("\n".join(current_config))

        return configs

    @classmethod
    def check_traceback_dumps(cls, additional_inclusion_criteria: list = []):
        import ast

        if additional_inclusion_criteria:
            if isinstance(additional_inclusion_criteria, str):
                additional_inclusion_criteria = [additional_inclusion_criteria]

            additional_inclusion_criteria = {
                f'"{criterium}"': "" if " " in criterium else criterium
                for criterium in additional_inclusion_criteria
            }

            if "sste_debug_errors_list" in cls.script_args:
                for key, value in additional_inclusion_criteria:
                    existing_sste_debug_errors_list = ast.literal_eval(
                        cls.script_args["sste_debug_errors_list"]
                    )
                    existing_sste_debug_errors_list[key] = value
                    cls.script_args[
                        "sste_debug_errors_list"
                    ] = existing_sste_debug_errors_list
            else:
                cls.script_args[
                    "sste_debug_errors_list"
                ] = additional_inclusion_criteria

        exit_run = sste_common.xr_check_trace_dump([], {}, cls.script_args, cls.testbed)
        if exit_run:
            return cls.failed("Error detected during traceback dump")
        else:
            cls.log("No error detected during traceback dump")

    @classmethod
    def rollback_testcase(cls, sequentially: bool = True):
        all_commits = cls.run_cmds(
            'show logging | inc "Configuration committed" | exc config_rollback',
            "show_logging_include_configuration_commit.textfsm",
        )
        if all_commits and "Commit_id" in all_commits.keys():
            all_commits = all_commits["Commit_id"]
            if sequentially:
                for commit_id in reversed(all_commits):
                    module_args = {
                        "sste_commands": [f"rollback configuration {commit_id}"]
                    }
                    output = sste_common.exec_commands(module_args, cls.script_args)

                    if any(
                        fail_text in output
                        for fail_text in [
                            "Rollback operation failed",
                            "failed verification",
                            "has not been modified",
                        ]
                    ):
                        # if "Please use the command 'show configuration failed rollback [inheritance]' to view the errors" in output:
                        #    module_args = {
                        #        "sste_commands": [f"show configuration failed rollback inheritance"]
                        #    }
                        #    sste_common.exec_commands(module_args, cls.script_args)
                        return cls.failed(
                            f"Unable to rollback configuration {commit_id}."
                        )
                cls.log(
                    "Config has been rolled back to the beginning of this testcase."
                )

            else:
                earliest_commit_id = all_commits[0]
                module_args = {
                    "sste_commands": [f"rollback configuration {earliest_commit_id}"]
                }
                output = sste_common.exec_commands(module_args, cls.script_args)

                if any(
                    fail_text in output
                    for fail_text in [
                        "Rollback operation failed",
                        "failed verification",
                        "has not been modified",
                    ]
                ):
                    # if "Please use the command 'show configuration failed rollback [inheritance]' to view the errors" in output:
                    #    module_args = {
                    #        "sste_commands": [f"show configuration failed rollback inheritance"]
                    #    }
                    #    sste_common.exec_commands(module_args, cls.script_args)
                    return cls.failed(
                        f"Unable to rollback configuration {earliest_commit_id}."
                    )
                else:
                    cls.log(
                        "Config has been rolled back to the beginning of this testcase."
                    )

        else:
            cls.log("No config is applied during the testcase. No config to roll back.")

    @classmethod
    def _parse_interface(cls, interface: str = "FourHundredGigE0/0/0/0"):
        interface_parser = re.compile(
            r"(?P<type>\w+)(?P<chassis>\d+)/(?P<lc>\d+)/(?P<pic>\d+)/(?P<port>\d+)"
        )
        parsed_output = interface_parser.match(interface)
        parsed_output = parsed_output.groupdict()
        parsed_output["chassis"] = int(parsed_output["chassis"])
        parsed_output["lc"] = int(parsed_output["lc"])
        parsed_output["pic"] = int(parsed_output["pic"])
        parsed_output["port"] = int(parsed_output["port"])
        return parsed_output

    @classmethod
    def get_local_topology(
        cls, sort="local", interested_devices: list = None, cli_criteria: list = []
    ):
        """
        Gets a list of interfaces and connection targets using show lldp neighbors.
        Can be sorted by local data ("local", default) or target data ("target")
        if interested_devices is None, get the full topology.
        Otherwise, only include ports with target_device that falls in interested_devices.
        """
        if isinstance(cli_criteria, str):
            cli_criteria = [cli_criteria]
        cmd = " | ".join(["show lldp neighbors"] + cli_criteria)
        neighbors = cls.run_cmds(cmd, "show_lldp_neighbors.textfsm", retries=5)
        neighbors = neighbors["system_name"]

        topology = {}
        interface_parser = re.compile(
            r"(?P<type>\w+)(?P<chassis>\d+)/(?P<lc>\d+)/(?P<pic>\d+)/(?P<port>\d+)"
        )

        if sort == "local":
            for target_device, neighbor_details in neighbors.items():
                if interested_devices is None or target_device in interested_devices:

                    if isinstance(neighbor_details["local_interface"], str):
                        local_interface, target_interface = (
                            neighbor_details["local_interface"],
                            neighbor_details["port_id"],
                        )
                        local_data, target_data = cls._parse_interface(
                            local_interface
                        ), cls._parse_interface(target_interface)
                        local_type, local_lc, local_port = (
                            local_data["type"],
                            local_data["lc"],
                            local_data["port"],
                        )
                        target_type, target_lc, target_port = (
                            target_data["type"],
                            target_data["lc"],
                            target_data["port"],
                        )

                        if local_lc not in topology.keys():
                            topology[local_lc] = {}

                        topology[local_lc][local_port] = {
                            "local_type": local_type,
                            "target_device": target_device,
                            "target_type": target_type,
                            "target_lc": target_lc,
                            "target_port": target_port,
                        }

                    else:
                        neighbor_details = neighbor_details["local_interface"]
                        for local_interface, data in neighbor_details.items():
                            target_interface = data["port_id"]
                            local_data, target_data = cls._parse_interface(
                                local_interface
                            ), cls._parse_interface(target_interface)
                            local_type, local_lc, local_port = (
                                local_data["type"],
                                local_data["lc"],
                                local_data["port"],
                            )
                            target_type, target_lc, target_port = (
                                target_data["type"],
                                target_data["lc"],
                                target_data["port"],
                            )

                            if local_lc not in topology.keys():
                                topology[local_lc] = {}

                            topology[local_lc][local_port] = {
                                "local_type": local_type,
                                "target_device": target_device,
                                "target_type": target_type,
                                "target_lc": target_lc,
                                "target_port": target_port,
                            }

        elif sort == "target":
            for target_device, neighbor_details in neighbors.items():
                if interested_devices is None or target_device in interested_devices:
                    if target_device not in topology.keys():
                        topology[target_device] = {}

                    if isinstance(neighbor_details["local_interface"], str):
                        local_interface, target_interface = (
                            neighbor_details["local_interface"],
                            neighbor_details["port_id"],
                        )
                        local_data, target_data = cls._parse_interface(
                            local_interface
                        ), cls._parse_interface(target_interface)
                        local_type, local_lc, local_port = (
                            local_data["type"],
                            local_data["lc"],
                            local_data["port"],
                        )
                        target_type, target_lc, target_port = (
                            target_data["type"],
                            target_data["lc"],
                            target_data["port"],
                        )

                        if target_lc not in topology[target_device].keys():
                            topology[target_device][target_lc] = {}

                        topology[target_device][target_lc][target_port] = {
                            "local_type": local_type,
                            "target_type": target_type,
                            "local_lc": local_lc,
                            "local_port": local_port,
                        }

                    else:
                        neighbor_details = neighbor_details["local_interface"]
                        for local_interface, data in neighbor_details.items():
                            target_interface = data["port_id"]
                            local_data, target_data = cls._parse_interface(
                                local_interface
                            ), cls._parse_interface(target_interface)
                            local_type, local_lc, local_port = (
                                local_data["type"],
                                local_data["lc"],
                                local_data["port"],
                            )
                            target_type, target_lc, target_port = (
                                target_data["type"],
                                target_data["lc"],
                                target_data["port"],
                            )

                            if target_lc not in topology[target_device].keys():
                                topology[target_device][target_lc] = {}

                            topology[target_device][target_lc][target_port] = {
                                "local_type": local_type,
                                "target_type": target_type,
                                "local_lc": local_lc,
                                "local_port": local_port,
                            }

        else:
            cls.log(
                f"get_local_topology() received unknown sorting criteria '{sort}'. It must be 'local' or 'target'",
                "warning",
            )

        return topology

    @classmethod
    def local_interfaces_from_topology(cls, topology):
        import itertools

        first_layer_keys = list(topology.keys())
        try:
            int(first_layer_keys[0])
            sort = "local"
        except ValueError as e:
            sort = "target"

        if sort == "local":
            interfaces = [
                [
                    f"{port_data['local_type']}0/{lc}/0/{port}"
                    for port, port_data in lc_data.items()
                ]
                for lc, lc_data in topology.items()
            ]
            interfaces = list(itertools.chain.from_iterable(interfaces))

        else:
            interfaces = [
                [
                    [
                        f"{target_port_data['local_type']}0/{target_port_data['local_lc']}/0/{target_port_data['local_port']}"
                        for target_port, target_port_data in target_lc_data.items()
                    ]
                    for target_lc, target_lc_data in target_device_data.items()
                ]
                for target_device, target_device_data in topology.items()
            ]
            interfaces = list(itertools.chain.from_iterable(interfaces))
            interfaces = list(itertools.chain.from_iterable(interfaces))

        return interfaces

    @classmethod
    def _count_interfaces(cls, local_topology, sort="local"):
        count = 0

        if sort == "local":
            for lc in local_topology.keys():
                num_ports = len(local_topology[lc].keys())
                count += num_ports

        elif sort == "target":
            for target_device in local_topology.keys():
                for lc in local_topology[target_device].keys():
                    num_ports = len(local_topology[target_device][lc].keys())
                    count += num_ports

        return count

    @classmethod
    def save_original_topology(
        cls, interested_devices: list = None, cli_criteria: list = []
    ):
        cls.test_data["original_topology"] = cls.get_local_topology(
            interested_devices=interested_devices, cli_criteria=cli_criteria
        )

    @classmethod
    def restore_topology(
        cls,
        target_topology=None,
        current_topology=None,
        current_topology_sorted_by="local",
        interested_devices: list = None,
        lldp_cli_criteria: list = [],
    ):
        if target_topology is None:
            if "original_topology" in cls.test_data.keys():
                target_topology = cls.test_data["original_topology"]
            else:
                return cls.failed(
                    "Cannot restore topology: test_data has no 'original_topology' and target_topology is unspecified"
                )

        target_topology = [
            f'{target_topology[lc][port]["local_type"]}0/{lc}/0/{port}'
            for lc in target_topology.keys()
            for port in target_topology[lc].keys()
        ]

        if current_topology is None:
            current_topology = cls.get_local_topology(
                interested_devices=interested_devices,
                sort=current_topology_sorted_by,
                cli_criteria=lldp_cli_criteria,
            )

        current_topology = (
            [
                f'{current_topology[lc][port]["local_type"]}0/{lc}/0/{port}'
                for lc in current_topology.keys()
                for port in current_topology[lc].keys()
            ]
            if current_topology_sorted_by == "local"
            else [
                f'{target_port_data["local_type"]}0/{target_port_data["local_lc"]}/0/{target_port_data["local_port"]}'
                for target_device, target_device_data in current_topology.items()
                for target_lc, target_lc_data in target_device_data.items()
                for target_port, target_port_data in target_lc_data.items()
            ]
        )

        interfaces_to_unshut = [
            interface
            for interface in target_topology
            if interface not in current_topology
        ]
        print_(f"unshutting {len(interfaces_to_unshut)} interfaces")

        interfaces_to_shut = [
            interface
            for interface in current_topology
            if interface not in target_topology
        ]
        print_(f"shutting {len(interfaces_to_shut)} interfaces")

        unshut_cmds = [
            f"no interface {interface} shutdown" for interface in interfaces_to_unshut
        ]

        shut_cmds = [
            f"interface {interface} shutdown" for interface in interfaces_to_shut
        ]

        cls.apply_configs(unshut_cmds + shut_cmds)

        cls.log("topology has been restored")

    @classmethod
    def _get_interfaces_by_lc(cls, topology=None, lldp_cli_criteria: list = []):
        if topology is None:
            topology = cls.get_local_topology(cli_criteria=lldp_cli_criteria)

        interfaces = [
            [
                f'{topology[lc][port]["local_type"]}0/{lc}/0/{port}'
                for port in topology[lc].keys()
            ]
            for lc in topology.keys()
        ]
        return interfaces

    @classmethod
    def _get_interfaces_by_target(cls, topology=None, lldp_cli_criteria: list = []):
        if topology is None:
            topology = cls.get_local_topology(
                sort="target", cli_criteria=lldp_cli_criteria
            )

        local_interfaces = [
            [
                f'{target_port_info["local_type"]}0/{target_port_info["local_lc"]}/0/{target_port_info["local_port"]}'
                for target_lc, target_lc_info in target_device_info.items()
                for target_port, target_port_info in target_lc_info.items()
            ]
            for target_device, target_device_info in topology.items()
        ]
        return local_interfaces

    @classmethod
    def keep_x_interfaces_unshut(
        cls,
        target_count: int,
        equal_distribution=True,
        sort="local",
        interested_devices: list = None,
        lldp_cli_criteria: list = [],
    ):
        """
        Uses show lldp neighbors to get the number of interfaces.
        If the number is less than
        """
        local_topology = cls.get_local_topology(
            interested_devices=interested_devices,
            sort=sort,
            cli_criteria=lldp_cli_criteria,
        )
        current_count = cls._count_interfaces(local_topology, sort=sort)
        print_(f"Current number of interfaces: {current_count}")

        need_more_interfaces = current_count < target_count

        if need_more_interfaces:
            print_(
                f"Need to restore original topology: the device has {current_count} interfaces but needs {target_count}"
            )
            if "original_topology" in cls.test_data.keys():
                original_count = cls._count_interfaces(
                    cls.test_data["original_topology"]
                )
                print_(f"Restoring interface count to {original_count}")

                cls.restore_topology(
                    current_topology=local_topology,
                    current_topology_sorted_by=sort,
                    lldp_cli_criteria=lldp_cli_criteria,
                )

                for attempt in range(5):
                    cls.log("Waiting for topology to stabilize")
                    cls.wait(60)

                    local_topology = cls.get_local_topology(
                        interested_devices=interested_devices,
                        sort=sort,
                        cli_criteria=lldp_cli_criteria,
                    )
                    current_count = cls._count_interfaces(local_topology, sort=sort)

                    print_(f"Current number of interfaces: {current_count}")

                    if current_count == original_count:
                        print_("The original topology is restored")
                        break

            else:
                cls.log(f"Cannot reach {target_count} interfaces", "warning")

        need_to_shut_interfaces = current_count > target_count
        if need_to_shut_interfaces:
            shut_count = current_count - target_count
            print_(f"Need to shut down {shut_count} interfaces")

            interfaces_to_shut = []

            if equal_distribution:
                if sort == "local":
                    all_interfaces = cls._get_interfaces_by_lc(
                        local_topology, lldp_cli_criteria=lldp_cli_criteria
                    )
                else:
                    all_interfaces = cls._get_interfaces_by_target(
                        local_topology, lldp_cli_criteria=lldp_cli_criteria
                    )

                print_(f"interfaces acquired = {all_interfaces}")
                [random.shuffle(interfaces) for interfaces in all_interfaces]

                print_(
                    f"choosing {shut_count} interfaces to shut down equally from {all_interfaces}"
                )
                for i in range(shut_count):
                    all_interfaces.sort(reverse=True, key=lambda x: len(x))
                    interfaces_to_shut.append(all_interfaces[0][0])
                    all_interfaces[0] = all_interfaces[0][1:]

            else:
                if sort == "local":
                    all_interfaces = [
                        f'{local_topology[lc][port]["local_type"]}0/{local_topology[lc]}/0/{local_topology[port]}'
                        for lc in local_topology.keys()
                        for port in local_topology[lc].keys()
                    ]
                else:
                    all_interfaces = [
                        f'{target_port_info["local_type"]}0/{target_port_info["local_lc"]}/0/{target_port_info["local_port"]}'
                        for target_device, target_device_info in local_topology.items()
                        for target_lc, target_lc_info in target_device_info.items()
                        for target_port, target_port_info in target_lc_info.items()
                    ]
                interfaces_to_shut = select_x(all_interfaces, shut_count)

            print_(
                f"shutting down {len(interfaces_to_shut)} interfaces: {interfaces_to_shut}"
            )
            shut_cmds = [
                f"interface {interface} shutdown" for interface in interfaces_to_shut
            ]

            cls.apply_configs(shut_cmds)
            cls.log(f"Number of interfaces remaining: {target_count}")
            return False
            # return target_count

        else:
            cls.log(f"Number of interfaces remaining: {current_count}")
            return need_more_interfaces or need_to_shut_interfaces
            # return current_count

    @classmethod
    def process_restart(cls, process_names, location="0/RP0/CPU0"):
        if isinstance(process_names, str):
            process_names = [process_names]

        return cls.run_cmds(
            [
                f"process restart {process_name} location {location}"
                for process_name in process_names
            ]
        )

    @classmethod
    def lc_reload(cls, lcs, wait=True):
        if isinstance(lcs, int):
            lcs = [lcs]

        successful = True

        saving_orig_check_convergence_time = "check_convergence_time" in cls.script_args
        if saving_orig_check_convergence_time:
            orig_check_convergence_time = cls.script_args["check_convergence_time"]

        cls.script_args["check_convergence_time"] = True
        for lc in lcs:
            reload_successful, _ = sste_trigger.swoir(
                cls.script_args, cls.testbed, {"node": f"0/{lc}/CPU0", "append": ""}
            )
            if reload_successful:
                cls.log(f"Successful in reloading LC {lc}")
            else:
                cls.log(f"Unsuccessful in reloading LC {lc}", "warning")
                successful = False

        if saving_orig_check_convergence_time:
            cls.script_args["check_convergence_time"] = orig_check_convergence_time

        if wait:
            cls.wait(10 * 60)

        return successful

    @classmethod
    def lc_reload_on_device(cls, device_name, lcs, wait=True):
        cls.run_on_router(device_name)(cls.lc_reload)(lcs, wait)

    @classmethod
    def reload_lc_after_commit_replace(cls, lcs: list):
        if (
            "need_to_reload_lcs" in cls.script_args
            and cls.script_args["need_to_reload_lcs"]
        ):
            cls.lc_reload(lcs=lcs)
            cls.script_args["need_to_reload_lcs"] = False

    @classmethod
    def show_tech(cls, specifications):
        if isinstance(specifications, str):
            specifications = [specifications]
        cmds = [
            f"show tech-support {specification}" for specification in specifications
        ]
        output = sste_common.exec_commands({"sste_commands": cmds}, cls.script_args)
        return output

    @classmethod
    def troubleshoot(
        cls,
        troubleshoot_level: str,
        additional_specifications_to_gather: List[str] = [],
    ):
        """
        Runs a series of troubleshooting commands.

        troubleshoot_level: str
            "failed" or "always". Will be compared with the "showtech" level from the yaml file to determine whether to proceed with the show tech commands.
        troubleshoot_categories: List[str]
            Will be translated to show tech-support specifications using troubleshoot_specifications.
            The options are defined in the keys of troubleshoot_specifications in this function, and "ixia" (which will collect ixia stats)
        additional_specifications_to_gather
            Other show tech-support specifications to gather with.
        """
        if isinstance(additional_specifications_to_gather, str):
            additional_specifications_to_gather = [additional_specifications_to_gather]

        def _troubleshoot_specifications(
            troubleshoot_categories: List[str],
        ) -> List[str]:
            if isinstance(troubleshoot_categories, str):
                troubleshoot_categories = [troubleshoot_categories]

            troubleshoot_specifications = {
                # only used to debug troubleshooting
                "troubleshoot_unit_test1": [
                    "show logging",
                    "show version",
                ],
                # only used to debug troubleshooting
                "troubleshoot_unit_test2": [
                    "show configuration commit changes last 1",
                ],
                "pfc": [
                    "show tech-support ofa",
                    "show tech-support qos pi",
                    "show tech-support qos platform",
                    "show tech-support platform-pfc",
                    "show tech-support platform",
                    "show tech-support fabric",
                    "show tech-support platform-fwd",
                    "show tech-support interface",
                    "show tech-support ethernet interfaces",
                    "show tech-support ethernet controllers",
                    "show asic-error all detail location 0/0/CPU0",
                    "show asic-error all detail location 0/1/CPU0",
                    "show asic-error all detail location 0/2/CPU0",
                    "show asic-error all detail location 0/3/CPU0",
                    "show asic-error all detail location 0/4/CPU0",
                    "show asic-error all detail location 0/5/CPU0",
                    "show asic-error all detail location 0/6/CPU0",
                    "show asic-error all detail location 0/7/CPU0",
                    "show controllers npu stats traps-all instance all location 0/0/CPU0",
                    "show controllers npu stats traps-all instance all location 0/1/CPU0",
                    "show controllers npu stats traps-all instance all location 0/2/CPU0",
                    "show controllers npu stats traps-all instance all location 0/3/CPU0",
                    "show controllers npu stats traps-all instance all location 0/4/CPU0",
                    "show controllers npu stats traps-all instance all location 0/5/CPU0",
                    "show controllers npu stats traps-all instance all location 0/6/CPU0",
                    "show controllers npu stats traps-all instance all location 0/7/CPU0",
                ],
                "bgp_convergence": [
                    "show tech-support routing bgp",
                    "show tech-support pfi",
                    "show tech-support ethernet interfaces",
                    "show tech-support optics",
                ],
                "bgp_table": [
                    "show lldp neighbors",
                    "show tech-support routing bgp",
                ],
                "sysdb": [],
            }

            troubleshoot_specifications = [
                troubleshoot_specifications[category]
                for category in troubleshoot_categories
                if category in troubleshoot_specifications.keys()
            ]
            troubleshoot_specifications = [
                specification
                for specifications in troubleshoot_specifications
                for specification in specifications
            ]
            return unique(troubleshoot_specifications)

        def _troubleshoot_level(level_txt):
            levels_definition = {
                "no": 2,
                "failed": 1,
                "always": 0,
            }

            try:
                if isinstance(level_txt, str):
                    return levels_definition[level_txt]
                else:
                    return int(level_txt)

            except (ValueError, KeyError) as e:
                print(
                    f"Cannot fetch troubleshoot level '{level_txt}'. Valid options are {', '.join(list(levels_definition.keys()))}"
                )
                return 0

        target_level = (
            cls.test_data["troubleshoot"]
            if "troubleshoot" in cls.test_data.keys()
            else "always"
        )
        troubleshoot_level = (
            troubleshoot_level
            if (troubleshoot_level == "failed" and not cls.testcase_passed)
            else "always"
        )
        target_level, current_level = _troubleshoot_level(
            target_level
        ), _troubleshoot_level(troubleshoot_level)

        time_to_troubleshoot = current_level >= target_level
        if time_to_troubleshoot:
            troubleshoot_categories = cls.troubleshoot_categories

            show_ixia_stats = "ixia" in troubleshoot_categories
            if show_ixia_stats:
                cls.sanity_traffic_check(cls, ixia_goal="show")

            troubleshoot_specifications = (
                _troubleshoot_specifications(troubleshoot_categories)
                + additional_specifications_to_gather
            )
            troubleshoot_specifications = unique(troubleshoot_specifications)
            if troubleshoot_specifications:
                cls.run_cmds(troubleshoot_specifications)

    @classmethod
    def lock_router(cls, router_name: str, new_password: str = "automation123"):
        try:
            config_data = {
                "purpose": f"Lock {router_name} for automation testing",
                "router": router_name,
                "cmds": [
                    "aaa authentication login VTY local group ISE-TAC-INBAND",
                    "aaa authentication login default local group ISE-TAC-INBAND",
                    "username cisco",
                    f"password {new_password}",
                    "exit",
                    "username lab",
                    f"password {new_password}",
                ],
            }
            cls.run_on_router(router_name)(cls.apply_configs)(config_data)

            cls.testbed.devices[router_name].credentials["default"][
                "password"
            ] = new_password

        except Exception as e:
            # got "TypeError: 'Testbed' object is not subscriptable" when doing cls.testbed["testbed"]["devices"][router_name]["credentials"]["default"]["password"] = new_password
            print(str(e))
            print(cls.testbed.devices[router_name])

    @classmethod
    def keep_running(cls):
        """
        To be passed into @aetest.skipUnless()'s condition.
        
        If test_data["abort_on_fail"] does not exist, return True
        If test_data["abort_on_fail"] is interpreted as False, return True
        If test_data["abort_on_fail"] is interpreted as True and no cls.failed() or cls.error() has been called, return True
        If test_data["abort_on_fail"] is interpreted as True and cls.failed() or cls.error() has been called, return False

        Example
        -------
        @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
        @aetest.test
        def verify_bgp_restored(self):
            Test.start_step("Wait for BGP to converge") \
                (Test.check_bgp_convergence)()
        """
        return True  # to be removed once troubleshooting is complete

        try:
            abort_on_fail = cls.test_data["abort_on_fail"]
        except KeyError as e:
            cls.test_data["abort_on_fail"] = False
            abort_on_fail = False
        except AttributeError as e:
            abort_on_fail = False
        try:
            automation_is_passing = cls.automation_is_passing
        except AttributeError as e:
            cls.automation_is_passing = True
            automation_is_passing = True

        return not abort_on_fail or automation_is_passing
