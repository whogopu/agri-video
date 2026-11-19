import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// Fanless Mac: keep concurrency moderate to limit thermal throttling. Tune in phase 5.
Config.setConcurrency(4);
