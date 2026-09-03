import { describe, expect, it } from "vitest";
import { SCHEMA_VERSION } from "./index";

describe("contracts", () => {
  it("pins a migratable schema version", () => expect(SCHEMA_VERSION).toBe("1.0"));
});
