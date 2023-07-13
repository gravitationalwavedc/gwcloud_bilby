import { setHarnessApi, harnessApi } from "../index";
import { createMockEnvironment } from "relay-test-utils";
import { expect } from "@jest/globals";

const newApi = {
  getEnvironment: () => createMockEnvironment(),
};

function setupHarnessApi() {
  setHarnessApi(null);
}

describe("app base route in index", () => {
  it("should set the harnessApi correctly", () => {
    expect.hasAssertions();
    setupHarnessApi();

    // harnessApi initial value should be null
    expect(harnessApi).toBeNull();

    // Set the harness api to our test api
    setHarnessApi(newApi);

    expect(harnessApi).toBe(newApi);
  });
});
