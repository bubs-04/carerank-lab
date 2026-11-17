import { defineConfig } from "vitest/config";
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_PROXY || "http://127.0.0.1:8000",
        configure(proxy) {
          proxy.on("proxyReq", (outgoing, incoming) => {
            outgoing.setHeader(
              "X-CareRank-Client-IP",
              incoming.socket.remoteAddress || "",
            );
            for (const header of ["X-Forwarded-For", "X-Real-IP", "Forwarded"])
              outgoing.removeHeader(header);
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.tsx"],
  },
});
