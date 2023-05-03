"""
@author Ben Hsieh
"""
import sys

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
from typing import Any, Union, Dict, List, Tuple

from parapyats import print_, Parent_Test, time_to_string, error_to_string
import re


class ECMP_Test(Parent_Test):
    @classmethod
    def clear_bgp_sessions_hard(cls):
        cls.run_cmds("clear bgp *")
        cls.wait(5 * 60)

    @classmethod
    def clear_bgp_sessions_soft(cls):
        cls.run_cmds(
            ["clear bgp ipv6 unicast * soft in", "clear bgp ipv6 unicast * soft out"]
        )

    @classmethod
    def show_bgp_neighbors(cls):
        cls.run_cmds("sh bgp ipv6 unicast summary wide")

    @classmethod
    def get_bgp_neighbor_count(cls):
        return cls.count_lines(
            'show bgp sessions | inc "{bgp_as}|6533[3,4]|6033[3,4]" | inc Established'
        )

    @classmethod
    def take_golden_bgp_neighbor_count(cls):
        cls.script_args["golden_bgp_neighbor_count"] = cls.get_bgp_neighbor_count()

    @classmethod
    def take_new_bgp_neighbor_count(cls):
        cls.script_args["new_bgp_neighbor_count"] = cls.get_bgp_neighbor_count()

    @classmethod
    def verify_bgp_neighbor_count_restored(cls):
        cls.take_new_bgp_neighbor_count()

        golden_count, new_count = (
            cls.script_args["golden_bgp_neighbor_count"],
            cls.script_args["new_bgp_neighbor_count"],
        )

        neighbor_count_matches = golden_count == new_count

        if neighbor_count_matches:
            cls.log(
                f"BGP neighbors are restored: new neighbor count ({new_count}) == original neighbor count ({golden_count})."
            )
            return True

        else:
            return cls.failed(
                f"BGP is not restored: new neighbor count ({new_count}) != original neighbor count ({golden_count})."
            )

    @classmethod
    def check_bgp_convergence(
        cls,
        convergence_attempts: int = 20,
        gap: int = 30,
        convergence_stability_requirement: int = 3,
    ):
        (
            seconds_expired,
            number_of_convergence_checks,
            number_of_convergences,
            longest_convergence_streaks,
        ) = (0, 0, 0, 0)
        unreachable_neighbor = ""
        for attempt in range(convergence_attempts):
            cls.log(f"BGP convergence attempt #{attempt+1}")

            converged = True
            for successive_convergences in range(convergence_stability_requirement):
                output = cls.run_cmds(
                    "show bgp ipv6 unicast convergence",
                    "show_bgp_ipv6_unicast_convergence.textfsm",
                    simple_output=True,
                )[0]
                number_of_convergence_checks += 1

                converged = output["Converged"] == "Converged"
                if converged:
                    print_(
                        f"Convergence is stable {successive_convergences+1}/{convergence_stability_requirement} times"
                    )
                    number_of_convergences += 1
                    longest_convergence_streaks = max(
                        longest_convergence_streaks, successive_convergences + 1
                    )

                    needs_more_checks = (
                        successive_convergences < convergence_stability_requirement - 1
                    )
                    if needs_more_checks:
                        cls.wait(10)
                        seconds_expired += 10
                else:
                    if output["First_unconverged_neighbor"]:
                        unreachable_neighbor = output["First_unconverged_neighbor"]
                    if successive_convergences > 0:
                        print_(
                            f"Convergence is unstable after {successive_convergences+1}/{convergence_stability_requirement} checks"
                        )
                    break

            time_elapsed = time_to_string(seconds_expired)
            if converged:
                cls.log(
                    f"BGP stably converged in {time_elapsed}. Total convergences: {number_of_convergences}/{number_of_convergence_checks} attempts."
                )
                return True

            else:
                cls.log(f"BGP has not converged stably in {time_elapsed}.")
                if attempt < convergence_attempts - 1:
                    cls.wait(gap)
                    seconds_expired += gap

        time_elapsed = time_to_string(seconds_expired)
        fail_txt = f"BGP did not converge stably within {time_elapsed}. Longest convergence streaks: {longest_convergence_streaks} (needs {convergence_stability_requirement}); Total convergences: {number_of_convergences}/{number_of_convergence_checks} attempts."

        if unreachable_neighbor:
            ping_output = cls.run_cmds(
                f"ping {unreachable_neighbor}", "ping.textfsm", simple_output=True
            )[0]
            rx, tx = int(ping_output["rx_count"]), int(ping_output["tx_count"])
            if rx == 0:
                fail_txt += f"\nFirst unreachable neighbor ({unreachable_neighbor}) cannot be ping'ed."
            elif rx != tx:
                fail_txt += f"\nFirst unreachable neighbor ({unreachable_neighbor}) can only be ping'ed {rx}/{tx} times."
            else:
                fail_txt += f"\nFirst unreachable neighbor ({unreachable_neighbor}) can be ping'ed stably."

        cls.run_cmds(f"show logging | include {unreachable_neighbor}")

        return cls.failed(fail_txt)

    @classmethod
    def take_bgp_peers_snapshot(cls):
        parsed_output = cls.run_cmds(
            "show bgp ipv6 unicast summary wide",
            "show_bgp_ipv6_unicast_summary_wide.textfsm",
        )
        cls.log("Got a snapshot of BGP peers.")
        return parsed_output

    @classmethod
    def take_golden_bgp_peers_snapshot(cls):
        cls.script_args["golden_bgp_snapshot"] = cls.take_bgp_peers_snapshot()

    @classmethod
    def take_new_bgp_peers_snapshot(cls):
        cls.script_args["new_bgp_snapshot"] = cls.take_bgp_peers_snapshot()

    @classmethod
    def verify_bgp_peers_restored(cls, attempts=20, gap=30):
        validation_pass = False
        for attempt in range(attempts):
            cls.log("BGP peer validation attempt: " + str(attempt + 1))
            cls.take_new_bgp_peers_snapshot()

            msg = []
            bgp_restored = sste_common.compare_dicts(
                cls.script_args["golden_bgp_snapshot"],
                cls.script_args["new_bgp_snapshot"],
                snapshot_value_range={},
                filenames=["Golden Snapshot", "New Snapshot"],
                exclude_keys={},
                msg=msg,
            )

            if bgp_restored:
                validation_pass = True
                break
            elif attempt < attempts - 1:
                cls.log("Difference(s) found. Next attempt starts in 30 seconds ...")
                cls.wait(gap)
            else:
                cls.log("Difference(s) found.")

        time_elapsed = time_to_string(attempt * gap)
        if validation_pass:
            cls.log(f"No difference found. BGP is restored in {time_elapsed}.")
            return True
        else:
            return cls.passx(
                f"BGP peers did not recover within {time_elapsed}."
            )  # TODO resolve passx vs fail

    @classmethod
    def verify_bgp_peers_drained(cls):
        snapshot = cls.take_bgp_peers_snapshot()
        for neighbor in snapshot["Neighbor"].keys():
            if int(snapshot["Neighbor"][neighbor]["St_PfxRcd"]) != 0:
                return cls.failed("Some of BGP peers' prefixes are non-zero.")

        cls.log("All BGP peers' prefixes are zero.")
        return True

    @classmethod
    def process_restart_bgp(cls, process="bgp", location="0/RP0/CPU0"):
        process_restart_cmd = ["process restart " + process + " location " + location]
        cls.run_cmds(process_restart_cmd)
        cls.wait(30)

    @classmethod
    def ensure_drain_policy_in_place(cls):
        output = cls.run_cmds("show run route-policy DRAIN")
        policy_in_place = "DRAIN" in output.split()

        if policy_in_place:
            cls.log("DRAIN POLICY is already configured")
            return True

        else:
            cls.apply_configs(["route-policy DRAIN", "drop", "end-policy"])
            cls.log("DRAIN POLICY has been configured")
            return True

    @classmethod
    def unconfigure_rpls(cls, as_number, bgp_neighbor_group_configs: dict):
        neighbor_configs = bgp_neighbor_group_configs["Neighbor_group"]
        config_in = [
            f"no router bgp {as_number} neighbor-group {neighbor_group} "
            + f"address-family {neighbor_configs[neighbor_group]['IP_type']} {neighbor_configs[neighbor_group]['Cast_type']} "
            + f"route-policy {neighbor_configs[neighbor_group]['Policy_in']} in"
            for neighbor_group in neighbor_configs.keys()
        ]
        config_out = [
            f"no router bgp {as_number} neighbor-group {neighbor_group} "
            + f"address-family {neighbor_configs[neighbor_group]['IP_type']} {neighbor_configs[neighbor_group]['Cast_type']} "
            + f"route-policy {neighbor_configs[neighbor_group]['Policy_out']} out"
            for neighbor_group in neighbor_configs.keys()
        ]

        cls.apply_configs(config_in + config_out)

        cls.log("All current RPLs are removed from neighbors")
        return True

    @classmethod
    def apply_drain_policies_to_rpls(cls, as_number, bgp_neighbor_group_configs: dict):
        neighbor_configs = bgp_neighbor_group_configs["Neighbor_group"]
        config_in = [
            f"router bgp {as_number} neighbor-group {neighbor_group} "
            + f"address-family {neighbor_configs[neighbor_group]['IP_type']} {neighbor_configs[neighbor_group]['Cast_type']} "
            + f"route-policy DRAIN in"
            for neighbor_group in neighbor_configs.keys()
        ]
        config_out = [
            f"router bgp {as_number} neighbor-group {neighbor_group} "
            + f"address-family {neighbor_configs[neighbor_group]['IP_type']} {neighbor_configs[neighbor_group]['Cast_type']} "
            + f"route-policy DRAIN out"
            for neighbor_group in neighbor_configs.keys()
        ]

        cls.apply_configs(config_in + config_out)

        cls.log("All current RPLs are have DRAIN policies")
        return True

    @classmethod
    def get_subnet_path_count(cls, receiver_type="intra_as"):
        current_router = cls.test_data["UUT"]

        if receiver_type == "intra_as":
            cls.switch_router(cls.test_data["intra_as_receiver"])
        else:
            cls.switch_router(cls.test_data["extra_as_receiver"])

        passed = True
        try:
            cls.clear_bgp_sessions_soft()

            cls.wait(10)

            subnet_data = cls.run_cmds(
                "show bgp ipv6 unicast {bgp_subnet} bestpath-compare",
                "show_bgp_ipv6_unicast_bestpath_compare.textfsm",
            )

            num_paths = int(subnet_data["Path"][""]["Total_paths"])
            cls.log(f"Number of paths: {num_paths}")

        except Exception as e:
            failed_message = error_to_string(e)
            cls.log(failed_message)
            print_(f"data format is: {subnet_data}")
            passed = False

        cls.switch_router(current_router)

        if passed:
            return num_paths

        else:
            return cls.failed(failed_message)

    @classmethod
    def set_xr_bgp_test6_data(
        cls, source_rtsw=1, ctsw=1, number_of_rtsws=8, extra_as_server="ASW-1"
    ):
        subnet = f"2001:{source_rtsw}{ctsw-1}:face::1/64"
        # subnet = f"2001:{source_rtsw}{ctsw-1}:face:21::/64"

        cls.test_data["bgp_subnet"] = subnet

        destination_rtsw_candidates = list(range(1, number_of_rtsws + 1))
        destination_rtsw_candidates.remove(source_rtsw)

        num_candidates = len(destination_rtsw_candidates)
        destination_rtsw = destination_rtsw_candidates[
            int(random.random() * num_candidates)
        ]

        cls.test_data["intra_as_receiver_num"] = destination_rtsw
        cls.test_data["intra_as_receiver"] = f"rtsw-{destination_rtsw}"

        cls.test_data["extra_as_receiver"] = extra_as_server

    @classmethod
    def set_bgp_timers(cls, testcase_name):
        deadtimer = cls.test_data["testcase_data"][testcase_name]["validate"][
            "deadtimer"
        ]
        keepalive = cls.test_data["testcase_data"][testcase_name]["validate"][
            "keepalive"
        ]
        bgp_as = cls.test_data["bgp_as"]
        config = f"router bgp {bgp_as} timers bgp {deadtimer} {keepalive}"
        try:
            cls.configure(config)
        except Exception as e:
            cls.log(str(e), log_type="error")
            return cls.failed(f"Apply config: failed")
        return True

    @classmethod
    def check_bgp_timers(cls, testcase_name, attempts=10, gap=30):

        validation_pass = False
        for attempt in range(attempts):
            try:
                # info = ["show bgp ipv6 unicast neighbors"]
                # ret = sste_common._get_snapshot_data(script_args, info)
                parsed_output = cls.run_cmds(
                    "show bgp ipv6 unicast neighbors",
                    "show_bgp_ipv6_unicast_neighbors.textfsm",
                )
                # cls.log(str(parsed_output))
                bgp_neighbors_dict = parsed_output["BGP_neighbor"]
                # cls.log(str(bgp_neighbors_dict))
                validation_pass = True
                for key in bgp_neighbors_dict:
                    item = bgp_neighbors_dict[key]
                    cls.log(str(item))
                    if "hold_time" in item:
                        cls.log(
                            cls.test_data["testcase_data"][testcase_name]["validate"][
                                "deadtimer"
                            ]
                        )
                        # cls.log(item["hold_time"])
                        if (
                            item["hold_time"]
                            == cls.test_data["testcase_data"][testcase_name][
                                "validate"
                            ]["deadtimer"]
                        ):
                            # if (not str(item["hold_time"]) == '') and (not str(item["hold_time"]) == cls.test_data['testcase_data'][testcase_name]['validate']['hold_time']):
                            validation_pass = False
                            cls.log("bgp hold_time setup failed", log_type="error")
                            cls.log("Error item: " + str(item), log_type="error")
                            break
                    if "keepalive_interval" in item:
                        # if (not str(item["keepalive_interval"]) == '') and (not str(item["keepalive_interval"]) == cls.test_data['testcase_data'][testcase_name]['validate']['keepalive_interval']):
                        if (
                            item["keepalive_interval"]
                            == cls.test_data["testcase_data"][testcase_name][
                                "validate"
                            ]["keepalive"]
                        ):
                            validation_pass = False
                            cls.log(
                                "bgp keepalive_interval setup failed", log_type="error"
                            )
                            cls.log("Error item: " + str(item), log_type="error")
                            break
            except Exception as e:
                cls.log(str(e), log_type="error")
                return cls.failed("BGP timer check: Failed")
            if validation_pass:
                # cls.log(str(parsed_output))
                cls.log("BGP timer check: passed")
                return True
            else:
                cls.log(
                    "bgp timer setup failed. config does not take effects within "
                    + str(attempt)
                    + " retries."
                )
                cls.log("Error item: " + str(item))

            cls.wait(gap)

        # cls.log(str(parsed_output))
        return cls.failed("BGP timer check: failed")

    @classmethod
    def load_config(cls, testcase_name, config_num=1):
        config = cls.test_data["testcase_data"][testcase_name]["configs"][config_num][
            "cmds"
        ]
        try:
            cls.configure(config)
        except Exception as e:
            cls.log(str(e), log_type="error")
            return cls.failed(f"Apply config: failed")
        return True

    @classmethod
    def get_source_device(cls, testcase_name, route=None):
        if not route:
            route = cls.test_data["testcase_data"][testcase_name]["route"]
        try:
            parsed_output = {"directly_connected": ""}
            while parsed_output["directly_connected"] == "":
                parsed_output = cls.run_cmds(
                    f"show route ipv6 {route}", "show_route_ipv6_get_source.textfsm"
                )
                route = parsed_output["next_hop"]
            source_interface = parsed_output["directly_connected"]
            device = int(source_interface.split("/")[1]) + 1
            cls.script_args["source_device"] = device
        except Exception as e:
            cls.log(str(e), log_type="error")
            return cls.failed(f"Get source interface for {route}: failed")
        return True

    @classmethod
    def set_and_validate_localpref(
        cls,
        testcase_name,
        route=None,
        rpl=None,
        attempts=10,
        gap=30,
        localpref_set=True,
    ):
        if not route:
            route = cls.test_data["testcase_data"][testcase_name]["route"]
        if not rpl:
            if "rpl" in cls.test_data["testcase_data"][testcase_name]:
                rpl = cls.test_data["testcase_data"][testcase_name]["rpl"]
            else:
                if not "source_device" in cls.script_args:
                    return cls.failed(f"No source device found for {route}")
                rpl = f"leaf_{str(cls.script_args['source_device'])}_srv_1_lp_in_v6"
        try:
            bgp_as = cls.test_data["bgp_as"]
            device = str(cls.script_args["source_device"])
            cls.apply_configs(
                [
                    f"router bgp {bgp_as} neighbor-group rtsw-leaf-{device} address-family ipv6 unicast",
                    f"route-policy {rpl} in",
                ]
            )
            cls.wait(60)
        except Exception as e:
            cls.log(str(e), log_type="error")
            return cls.failed(f"BGP set Local Preference for {route}: failed")

        if localpref_set:
            localpref = str(
                cls.test_data["testcase_data"][testcase_name]["validate"]["localpref"]
            )
            for attempt in range(attempts):
                try:
                    # parsed_output = cls.run_cmds(f"show bgp ipv6 unicast {route} bestpath-compare", "show_bgp_ipv6_unicast_route_bestpath_compare.textfsm")
                    output = cls.run_cmds(
                        f"show bgp ipv6 unicast {route} bestpath-compare | include localpref {localpref}"
                    )
                    if localpref in output:
                        cls.log(f"BGP local pref is set to {localpref}")
                        cls.log("BGP local pref validation: passed")
                        return True
                    else:
                        cls.log(
                            "BGP local pref validation failed. config does not take effects within "
                            + str(attempt)
                            + " retries."
                        )
                except Exception as e:
                    cls.log(str(e), log_type="error")

                cls.wait(gap)

            return cls.failed(f"BGP Local Preference Validation for {route}: failed")

        else:
            localpref = str(
                cls.test_data["testcase_data"][testcase_name]["validate"]["localpref"]
            )
            for attempt in range(attempts):
                try:
                    # parsed_output = cls.run_cmds(f"show bgp ipv6 unicast {route} bestpath-compare", "show_bgp_ipv6_unicast_route_bestpath_compare.textfsm")
                    output = cls.run_cmds(
                        f"show bgp ipv6 unicast {route} bestpath-compare | include localpref {localpref}"
                    )
                    if localpref in output:
                        cls.log(
                            f"BGP local pref {localpref} found in paths, validation failed within "
                            + str(attempt)
                            + " retries."
                        )
                    else:
                        cls.log(f"No BGP local pref is set to {localpref}")
                        cls.log("BGP local pref validation: passed")
                        return True
                except Exception as e:
                    cls.log(str(e), log_type="error")

                cls.wait(gap)

            return cls.failed(f"BGP Local Preference Validation for {route}: failed")

    @classmethod
    def get_lldp_neighbors_by_devices(cls, interested_devices: List[str]):
        interfaces_split_by_devices = cls.get_local_topology(
            sort="target", interested_devices=interested_devices
        )

        interfaces_split_by_devices = {
            target_device: [
                f"FourHundredGigE0/{target_port_info['local_lc']}/0/{target_port_info['local_port']}"
                for target_lc, target_lc_info in target_device_info.items()
                for target_port, target_port_info in target_lc_info.items()
                if target_port_info["local_type"] == "FourHundredGigE"
            ]
            for target_device, target_device_info in interfaces_split_by_devices.items()
        }

        return interfaces_split_by_devices

    @classmethod
    def get_traffic_data(cls):
        return cls.run_cmds(
            "show interfaces counters rates physical",
            "show_interfaces_counters_rates_physical.textfsm",
        )

    @classmethod
    def get_traffic_data_for_interfaces(cls, interfaces: list):
        if not isinstance(interfaces, list):
            interfaces = [interfaces]

        rates = [
            cls.run_cmds(
                f'show interfaces {interface} | inc "output rate"',
                "show_interface_interface",
                simple_output=True,
            )
            for interface in interfaces
        ]

        rates = [int(rate[0]["output_rate"]) if len(rate) > 0 else 0 for rate in rates]
        return rates

    @classmethod
    def get_traffic_stats_for_each_device(
        cls, interested_devices: List[str], stat_name: str = "OutMbps"
    ):
        """
        output structure: {
            "rtsw-1": [175.5, 174.7],
            "rtsw-2": [186.3, 188.5],
        }
        """
        interfaces_split_by_devices = cls.get_lldp_neighbors_by_devices(
            interested_devices
        )

        traffic_data_by_devices = {
            target_device: cls.get_traffic_data_for_interfaces(local_ports)
            for target_device, local_ports in interfaces_split_by_devices.items()
        }
        """
        traffic_data = cls.get_traffic_data()

        traffic_data_by_devices = {
            target_device: [
                float(traffic_data["Interface"][local_port][stat_name])
                if local_port in traffic_data["Interface"].keys()
                else 0.0
                for local_port in local_ports
            ]
            for target_device, local_ports in interfaces_split_by_devices.items()
        }
        """

        return traffic_data_by_devices

    @classmethod
    def verify_similar_rates(cls, data: List[float], threshold: float, stdev: int):
        # method: minimum >= 80% average
        sample_size = len(data)
        average = sum(data) / sample_size
        theoretical_minimum = 0.8*average
        minimum = min(data)

        minimum_is_in_range = minimum >= theoretical_minimum

        theoretical_minimum = format(theoretical_minimum, ".2f").rstrip("0").rstrip(".")
        minimum = format(minimum, ".2f").rstrip("0").rstrip(".")
        if minimum_is_in_range:
            cls.log("All frames have similar rates.")
            # cls.log(f"All rates (minimum: {minimum}) are at least 50% of the average (50% {average} = {theoretical_minimum})")
            return True
        else:
            fail_summary = "Gap in frame rates is too high."
            # fail_summary = f"minimum rate ({minimum}) < 50% of the average (50% {average} = {theoretical_minimum})"
            return cls.failed(fail_summary)

        """
        # method: average +/- stdev*standard_deviation
        from math import pow, sqrt
        sample_size = len(data)
        average = sum(data) / sample_size
        standard_deviation = sqrt(sum([pow(x-average, 2) for x in data])/sample_size)
        theoretical_maximum = average + stdev*standard_deviation
        theoretical_minimum = average - stdev*standard_deviation
        maximum = max(data)
        minimum = min(data)

        maximum_is_in_range, minimum_is_in_range = maximum <= theoretical_maximum, minimum >= theoretical_minimum
        
        average = format(average, '.2f').rstrip("0").rstrip(".")
        standard_deviation = format(standard_deviation, '.2f').rstrip("0").rstrip(".")
        theoretical_maximum = format(theoretical_maximum, '.2f').rstrip("0").rstrip(".")
        theoretical_minimum = format(theoretical_minimum, '.2f').rstrip("0").rstrip(".")
        minimum = format(minimum, '.2f').rstrip("0").rstrip(".")
        maximum = format(maximum, '.2f').rstrip("0").rstrip(".")
        cls.log(f"Average: {average}, standard deviation: {standard_deviation}, average +/- {stdev} standard deviations: ({theoretical_minimum}, {theoretical_maximum}), range: ({minimum}, {maximum})")

        fail_summary = []
        if not minimum_is_in_range:
            fail_summary.append(f"minimum rate ({minimum}) < average-{stdev} standard deviations ({theoretical_minimum})")
        if not maximum_is_in_range:
            fail_summary.append(f"maximum rate ({maximum}) > average+{stdev} standard deviations ({theoretical_maximum})")
        fail_summary = '\n'.join(fail_summary)

        if fail_summary:
            return cls.failed(fail_summary)
        else:
            cls.log(f"All rates fall within average +/- {stdev} standard deviations")
            return True
        """

        """
        # method: average +/- threshold
        average = sum(data) / len(data)
        theoretical_maximum = average+threshold
        theoretical_minimum = average-threshold
        maximum = max(data)
        minimum = min(data)

        passed = (maximum <= theoretical_maximum) and (minimum >= theoretical_minimum)

        average, minimum, maximum = format(average, '.2f').strip("0"), format(minimum, '.2f').strip("0"), format(maximum, '.2f').strip("0")
        summary = f"Average: {average}, Range: ({minimum}, {maximum})"

        if passed:
            cls.log(summary)
            return True
        
        else:
            return cls.failed(summary)
        """

    @classmethod
    def check_traffic_loss(cls, traffic_num: int = 1, passx_threshold: int = None):
        """
        For each traffic item within the traffic group (defined in cls.test_data), check it against the passx_threshold to determine if there is:
        1. no loss at all (Loss % = 0),
        2. no significant loss (0 < Loss % <= passx_threshold), or
        3. significant loss (Loss % > passx_threshold).

        passx_threshold can be defined in four ways:
        1. 0 by default,
        2. globally, in cls.test_data["acceptable_traffic_loss_threshold"] (overriding the default value),
        3. for a testcase, in cls.test_data[<testcase_name>]["acceptable_traffic_loss_threshold"] (overriding the global definition), or
        4. as this function's parameter (overriding both global and testcase definitions).
        """
        traffic_stats = cls.get_ixia_stats(traffic_num, ["Loss %"])

        if passx_threshold is None:
            passx_threshold = (
                cls.test_data["acceptable_traffic_loss_threshold"]
                if "acceptable_traffic_loss_threshold" in cls.test_data.keys()
                else 0
            )
            passx_threshold = (
                cls.test_data["testcase_data"][cls.testcase][
                    "acceptable_traffic_loss_threshold"
                ]
                if "acceptable_traffic_loss_threshold"
                in cls.test_data["testcase_data"][cls.testcase].keys()
                else passx_threshold
            )

        no_loss, no_significant_loss, significant_loss = [], [], []
        for traffic_name, stats in traffic_stats.items():
            loss = stats["Loss %"]
            if loss == 0:
                no_loss.append(
                    (traffic_name, format(loss, ".2f").rstrip("0").rstrip("."))
                )
                print_(f"no loss detected in {traffic_name}")
            elif loss <= passx_threshold:
                no_significant_loss.append(
                    (traffic_name, format(loss, ".2f").rstrip("0").rstrip("."))
                )
                print_(f"no significant loss detected in {traffic_name}")
            else:
                significant_loss.append(
                    (traffic_name, format(loss, ".2f").rstrip("0").rstrip("."))
                )
                print_(f"significant loss detected in {traffic_name}")

        passx_threshold = format(passx_threshold, ".2f").rstrip("0").rstrip(".")

        failed = len(significant_loss) > 0
        passx = not failed and len(no_significant_loss) > 0
        passed = not failed and not passx

        no_loss = [
            f"{traffic_name} (loss = {loss}%) has no traffic loss (acceptable loss threshold={passx_threshold})"
            for traffic_name, loss in no_loss
        ]

        no_significant_loss = [
            f"{traffic_name} (loss = {loss}%) has no significant traffic loss (acceptable loss threshold={passx_threshold})"
            for traffic_name, loss in no_significant_loss
        ]

        significant_loss = [
            f"{traffic_name} (loss = {loss}%) has significant traffic loss (acceptable loss threshold={passx_threshold})"
            for traffic_name, loss in no_significant_loss
        ]

        traffic_loss_logs = "\n".join(no_loss + no_significant_loss + significant_loss)

        if passed:
            cls.log(traffic_loss_logs)
            return True
        elif passx:
            return cls.passx(traffic_loss_logs)
        else:
            return cls.failed(traffic_loss_logs)
