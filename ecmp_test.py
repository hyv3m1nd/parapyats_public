#!/bin/env python
import sys, inspect

sys.path.append("cafykit/lib/")

from pyats import aetest
from pyats.aetest.loop import Iteration
from pyats.easypy import run
from ats.log.utils import banner
import logging
import sste_common, sste_exr, sste_cxr, sste_trigger, sste_cli_keys, sste_spitfire, sste_tgn

import yaml, pdb, json
from texttable import Texttable
import re, random, time, collections
from functools import reduce
from time import time, sleep
from typing import Any, Union
from cgi import test

from parapyats import tree, print_
from ecmp_parapyats import ECMP_Test as Test

Test.set_logger(__name__)


class CommonSetup(aetest.CommonSetup):
    @aetest.subsection
    def build_parapyats_system(self, testscript, testbed, steps, test_data):
        Test.initialize()
        Test.set_params(
            testscript=testscript,
            testbed=testbed,
            steps=steps,
            test_data=test_data,
        )

    @aetest.subsection
    def establish_connections(self):
        target_router = Test.test_data["UUT"]
        Test.start_step(f"Ssh into {target_router}") \
            (Test.connect_to_uut)()

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.subsection
    def backup_configs(self):
        golden_config_devices = (
            list(Test.test_data["golden_configs"].keys())
            if "golden_configs" in Test.test_data.keys()
            else []
        )
        lock_devices = (
            Test.test_data["lock_devices"]
            if "lock_devices" in Test.test_data.keys()
            else []
        )
        devices_to_back_up = list(set(golden_config_devices + lock_devices))

        for device_name in devices_to_back_up:
            Test.start_step(f"Back up current configurations for {device_name}") \
            (Test.backup_running_config)(target_router=device_name)

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.subsection
    def configure_devices(self):
        golden_config_devices = (
            list(Test.test_data["golden_configs"].keys())
            if "golden_configs" in Test.test_data.keys()
            else []
        )
        for device_name in golden_config_devices:
            Test.start_step(f"Apply golden config to {device_name}") \
            (Test.apply_golden_configs)(target_router=device_name)

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.subsection
    def initialize_ixia_traffic_items(self):
        if "tgn" in Test.test_data:
            Test.start_step("Connect to traffic generator") \
                (Test.connect_to_tgn)()

            Test.start_step("Identify IXIA traffic items") \
                (Test.identify_ixia_traffic)()

            Test.start_step("Disable all ixia traffic") \
                (Test.disable_all_ixia_traffic)()

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.subsection
    def set_test_parameters(self):
        Test.start_step("Set test parameters") \
            (Test.set_test_parameters)()

        testcases = Test.start_step("Get testcases") \
            (Test.get_testcases)(__name__)

        Test.start_step("Skip inactive testcases") \
            (Test.skip_inactive_tests)(testcases)

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.subsection
    def take_topology_snapshot(self):
        Test.start_step("Get topology") \
            (Test.save_original_topology)(cli_criteria="inc <leaf names' common prefix>")

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.subsection
    def ensure_bgp_is_stable(self):
        Test.start_step("Clear BGP sessions") \
            (Test.clear_bgp_sessions_hard)()

        Test.troubleshootable_step("Wait for BGP to converge", troubleshoot_categories="bgp_convergence") \
            (Test.check_bgp_convergence)(convergence_attempts=11)

        Test.start_step("Get the number of BGP neighbors") \
            (Test.take_golden_bgp_neighbor_count)()

        Test.start_step("Take an initial snapshot of all BGP peers") \
            (Test.take_golden_bgp_peers_snapshot)()

        Test.start_step("Wait for BGP peers to change") \
            (Test.wait)(5 * 60)

        Test.start_step("Verify BGP snapshot is unchanged") \
            (Test.verify_bgp_peers_restored)()


@aetest.skipUnless(Test.keep_running(), "Automation has failed already")
class xr_ecmp_test1(aetest.Testcase):
    """
    Verify BGP session timers modification
    """

    @aetest.setup
    def testcase_setup(self, steps, section):
        Test.set_params(section=section, testcase=f"{self.__class__.__name__}", steps=steps)
        Test.start_step(f"Display test plan for {self.__class__.__name__}", continue_=True) \
            (Test.testcase_overview)(self.__class__.__name__)

        Test.start_step(f"Clear log and context") \
            (Test.run_cmds)(["clear logging", "clear context"])

        Test.start_step(f"Shut down BGP neighbors on <router1's name>") \
            (Test.apply_testcase_configs)(1)

        Test.start_step("Start ixia traffic") \
            (Test.start_ixia_traffic)(1, max_apply_attempts=7)

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    def _verify_ecmp(self, num_paths, threshold: int = 0.9, stdev: int = 2):
        continue_ = True
        interested_devices = [f"<leaf_{leaf_num}'s name" for leaf_num in range(1, 9)]
        changes_made = Test.start_step(f"Keep {num_paths} interfaces") \
            (Test.keep_x_interfaces_unshut)(target_count=num_paths, interested_devices=interested_devices, sort="target", lldp_cli_criteria="inc <leaf names' common prefix>")

        if changes_made:
            Test.start_step("Wait for all interfaces to stabilize") \
                (Test.wait)(5 * 60)

            Test.start_step(f"Ensure {num_paths} interfaces are kept") \
            (Test.keep_x_interfaces_unshut)(target_count=num_paths, interested_devices=interested_devices, sort="target", lldp_cli_criteria="inc <leaf names' common prefix>")

        Test.troubleshootable_step(f"Verify that {num_paths} paths exists in the BGP table", continue_=continue_, troubleshoot_categories="bgp_table") \
            (Test.verify_line_count)("show bgp ipv6 unicast {multipath_ip}", "inc multipath", "==", num_paths, f"{num_paths} paths in the BGP table")

        traffic_data_by_rtsws = Test.start_step(f"Get outbound packets for each rtsw") \
            (Test.get_traffic_stats_for_each_device)(interested_devices=interested_devices, stat_name="OutMbps")

        print_(traffic_data_by_rtsws)

        all_traffic_data = [
            data_point
            for rtsw, traffic_data in traffic_data_by_rtsws.items()
            for data_point in traffic_data
        ]
        Test.start_step(f"Ensure the outbound packet rates for all interfaces fall within 3 standard deviations of the average rate") \
            (Test.verify_similar_rates)(data=all_traffic_data, threshold=threshold, stdev=stdev)

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.test.loop(num_paths=[64, 32, 16, 8])
    def verify_ecmp(self, num_paths):
        self._verify_ecmp(num_paths)

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.test
    def verify_no_traffic_loss(self):
        Test.start_step("Stop IXIA traffic") \
            (Test.stop_ixia_traffic)(1)

        Test.wait(10)

        Test.start_step("Verify no traffic loss") \
            (Test.check_traffic_loss)(traffic_num=1)

    @aetest.cleanup
    def testcase_cleanup(self):
        Test.start_step("Stop all ixia traffic", continue_=True) \
            (Test.stop_ixia_traffic)(1)

        Test.start_step("Gather troubleshooting logs", continue_=True) \
            (Test.troubleshoot)(troubleshoot_level="failed")

        Test.start_step("Check traceback and dumps") \
            (Test.check_traceback_dumps)()


class CommonCleanup(aetest.CommonCleanup):
    # @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    # @aetest.subsection
    def restore_pretest_config(self):
        golden_config_devices = (
            list(Test.test_data["golden_configs"].keys())
            if "golden_configs" in Test.test_data.keys()
            else []
        )
        lock_devices = (
            Test.test_data["lock_devices"]
            if "lock_devices" in Test.test_data.keys()
            else []
        )
        all_configured_devices = list(set(golden_config_devices + lock_devices))

        for device_name in all_configured_devices:
            Test.start_step("Load pre-test configurations", continue_=True) \
            (Test.restore_running_config)(target_router=device_name)

            lcs = 8
            wait = device_name == all_configured_devices[-1]
            Test.start_step(f"Reload LCs on {device_name}", continue_=True) \
            (Test.lc_reload_on_device)(device_name, lcs, wait)

    @aetest.skipUnless(Test.keep_running(), "Automation has failed already")
    @aetest.subsection
    def unshut_bgp_neighbors_on_ctsw1(self):
        Test.start_step("Rollback BGP neighbors on <router1's name>") \
            (Test.rollback_config_on_device)("<router1's name>")

    @aetest.subsection
    def disconnect(self):
        Test.start_step("Disconnect from all devices", continue_=True) \
            (Test.disconnect)()

    @aetest.subsection
    def display_timing_report(self):
        Test.start_step("Display timing report", continue_=True) \
            (Test.display_timing_report)()

    @aetest.subsection
    def upload_log(self):
        Test.start_step("Upload log", continue_=True) \
            (Test.upload_log)()
