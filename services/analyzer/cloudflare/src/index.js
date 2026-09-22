import { Container, getContainer } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

export class AnalyzerContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "10m";
  enableInternet = true;
  envVars = {
    INTERNAL_TOKEN: env.INTERNAL_TOKEN || "",
    ANALYZER_PIPELINE_VERSION: "cloudflare-container",
    PDF_NATIVE_TEXT_FASTPATH: "1",
  };
}

export default {
  async fetch(request, bindings) {
    return getContainer(bindings.ANALYZER_CONTAINER, "primary").fetch(request);
  },
};
