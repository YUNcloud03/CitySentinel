export const MIN_PEDESTRIAN_CLEARANCE_SECONDS = 8;
export const MAX_SIGNAL_RECOVERY_SECONDS = 30;

type CorridorSafetyInput = {
  signal_actions: {
    intersection_id: string;
    prepare_at_seconds: number;
    activate_at_seconds: number;
    passage_at_seconds: number;
    restore_at_seconds: number;
    pedestrian_clearance_seconds: number;
  }[];
  runtime_state: {
    intersection_states: { intersection_id: string; state: string }[];
  };
};

export function corridorSafetyViolations(result: CorridorSafetyInput): string[] {
  const violations: string[] = [];
  for (const action of result.signal_actions) {
    if (action.pedestrian_clearance_seconds < MIN_PEDESTRIAN_CLEARANCE_SECONDS) {
      violations.push(`${action.intersection_id}: pedestrian clearance below minimum`);
    }
    if (action.activate_at_seconds - action.prepare_at_seconds < action.pedestrian_clearance_seconds) {
      violations.push(`${action.intersection_id}: activation starts before pedestrian clearance completes`);
    }
    if (action.restore_at_seconds - action.passage_at_seconds > MAX_SIGNAL_RECOVERY_SECONDS) {
      violations.push(`${action.intersection_id}: signal recovery exceeds maximum`);
    }
  }
  const activeIntersections = new Set(
    result.runtime_state.intersection_states
      .filter((row) => row.state === "EMERGENCY_GREEN")
      .map((row) => row.intersection_id),
  );
  if (activeIntersections.size > 1) violations.push("more than one intersection has emergency green");
  return violations;
}
