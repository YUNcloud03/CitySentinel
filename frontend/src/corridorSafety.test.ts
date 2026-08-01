import { describe, expect, it } from "vitest";
import {
  corridorSafetyViolations,
  MAX_SIGNAL_RECOVERY_SECONDS,
  MIN_PEDESTRIAN_CLEARANCE_SECONDS,
} from "./corridorSafety";

function safeCorridor() {
  return {
    signal_actions: [{
      intersection_id: "I-001",
      prepare_at_seconds: 10,
      activate_at_seconds: 18,
      passage_at_seconds: 25,
      restore_at_seconds: 37,
      pedestrian_clearance_seconds: 8,
    }],
    runtime_state: {
      intersection_states: [
        { intersection_id: "I-001", state: "EMERGENCY_GREEN" },
        { intersection_id: "I-002", state: "WAITING" },
      ],
    },
  };
}

describe("green corridor safety invariants", () => {
  it("accepts pedestrian clearance and recovery within policy", () => {
    expect(MIN_PEDESTRIAN_CLEARANCE_SECONDS).toBe(8);
    expect(MAX_SIGNAL_RECOVERY_SECONDS).toBe(30);
    expect(corridorSafetyViolations(safeCorridor())).toEqual([]);
  });

  it("rejects early activation and recovery over 30 seconds", () => {
    const corridor = safeCorridor();
    corridor.signal_actions[0].pedestrian_clearance_seconds = 9;
    corridor.signal_actions[0].activate_at_seconds = 18;
    corridor.signal_actions[0].restore_at_seconds = 56;
    expect(corridorSafetyViolations(corridor)).toEqual(expect.arrayContaining([
      expect.stringContaining("before pedestrian clearance"),
      expect.stringContaining("recovery exceeds"),
    ]));
  });

  it("never permits emergency green at two intersections", () => {
    const corridor = safeCorridor();
    corridor.runtime_state.intersection_states[1].state = "EMERGENCY_GREEN";
    expect(corridorSafetyViolations(corridor)).toContain("more than one intersection has emergency green");
  });
});
