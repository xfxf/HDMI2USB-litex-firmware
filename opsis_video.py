#!/usr/bin/env python3
from opsis_base import *

from litevideo.input import HDMIIn
from litevideo.output import VideoOut

from litescope import LiteScopeAnalyzer

base_cls = MiniSoC


class VideoMixerSoC(base_cls):
    csr_peripherals = (
        "hdmi_out0",
        "hdmi_out1",
        "hdmi_in0",
        "hdmi_in0_edid_mem",
        "hdmi_in1",
        "hdmi_in1_edid_mem",
        "analyzer",
    )
    csr_map_update(base_cls.csr_map, csr_peripherals)

    interrupt_map = {
        "hdmi_in0": 3,
        "hdmi_in1": 4,
    }
    interrupt_map.update(base_cls.interrupt_map)

    def __init__(self, platform, **kwargs):
        base_cls.__init__(self, platform, **kwargs)
        # hdmi in 0
        self.submodules.hdmi_in0 = HDMIIn(platform.request("hdmi_in", 0),
                                          self.sdram.crossbar.get_port(mode="write"),
                                          fifo_depth=512)
        # hdmi in 1
        self.submodules.hdmi_in1 = HDMIIn(platform.request("hdmi_in", 1),
                                          self.sdram.crossbar.get_port(mode="write"),
                                          fifo_depth=512)
        # hdmi out 0
        self.submodules.hdmi_out0 = VideoOut(platform.device,
                                            platform.request("hdmi_out", 0),
                                            self.sdram.crossbar.get_port(mode="read", dw=16, cd="hdmi_out0_pix", reverse=True),
                                            mode="ycbcr422",
                                            fifo_depth=4096)
        # hdmi out 1 : Share clocking with hdmi_out0 since no PLL_ADV left.
        self.submodules.hdmi_out1 = VideoOut(platform.device,
                                            platform.request("hdmi_out", 1),
                                            self.sdram.crossbar.get_port(mode="read", dw=16, cd="hdmi_out1_pix", reverse=True),
                                            mode="ycbcr422",
                                            fifo_depth=4096,
                                            external_clocking=self.hdmi_out0.driver.clocking)

        # all PLL_ADV are used: router needs help...
        platform.add_platform_command("""INST PLL_ADV LOC=PLL_ADV_X0Y0;""")
        # FIXME: Fix the HDMI out so this can be removed.
        platform.add_platform_command(
            """PIN "hdmi_out_pix_bufg.O" CLOCK_DEDICATED_ROUTE = FALSE;""")
        platform.add_platform_command(
            """PIN "hdmi_out_pix_bufg_1.O" CLOCK_DEDICATED_ROUTE = FALSE;""")
        platform.add_platform_command(
            """
NET "{pix0_clk}" TNM_NET = "GRPpix0_clk";
NET "{pix1_clk}" TNM_NET = "GRPpix1_clk";
""",
                pix0_clk=self.hdmi_out0.driver.clocking.cd_pix.clk,
                pix1_clk=self.hdmi_out1.driver.clocking.cd_pix.clk,
        )
        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.hdmi_out0.driver.clocking.cd_pix.clk,
            self.hdmi_out1.driver.clocking.cd_pix.clk)

        analyzer_signals = [
            self.hdmi_in0.chansync.valid_i,
            self.hdmi_in0.chansync.data_in0,
            self.hdmi_in0.chansync.data_in1,
            self.hdmi_in0.chansync.data_in2,
        ]
        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals, 2048, cd="hdmi_in0_pix")

    def do_exit(self, vns, filename="test/analyzer.csv"):
        self.analyzer.export_csv(vns, filename)



def main():
    parser = argparse.ArgumentParser(description="Opsis LiteX SoC")
    builder_args(parser)
    soc_sdram_args(parser)
    parser.add_argument("--nocompile-gateware", action="store_true")
    parser.add_argument("--iprange", default="192.168.100")
    args = parser.parse_args()

    platform = opsis_platform.Platform()
    soc = VideoMixerSoC(platform, **soc_sdram_argdict(args))
    soc.configure_iprange(args.iprange)
    builddir = "build/opsis_video/"
    testdir = "{}/test".format(builddir)

    builder = Builder(soc, output_dir=builddir,
                      compile_gateware=not args.nocompile_gateware,
                      csr_csv="{}/csr.csv".format(testdir))
    builder.add_software_package("libuip", "{}/firmware/libuip".format(os.getcwd()))
    builder.add_software_package("firmware", "{}/firmware".format(os.getcwd()))
    if not os.path.exists(testdir):
        os.makedirs(testdir) # FIXME: Remove when builder does this.
    vns = builder.build()
    soc.do_exit(vns, "{}/analyzer.csv".format(testdir))


if __name__ == "__main__":
    main()
