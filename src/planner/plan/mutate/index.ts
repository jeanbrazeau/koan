// Re-exports all public mutation functions grouped by domain.
// Consumers import from this single entry point.

export {
  setOverview,
  setConstraints,
  setInvisibleKnowledge,
} from "./top-level.js";

export {
  addDecision,
  setDecision,
  addRejectedAlternative,
  setRejectedAlternative,
  addRisk,
  setRisk,
} from "./decisions.js";

export {
  addMilestone,
  setMilestoneName,
  setMilestoneFiles,
  setMilestoneFlags,
  setMilestoneRequirements,
  setMilestoneAcceptanceCriteria,
  setMilestoneTests,
} from "./milestones.js";

export {
  addIntent,
  setIntent,
  addChange,
  setChangeDiff,
  setChangeDocDiff,
  setChangeComments,
  setChangeFile,
  setChangeIntentRef,
} from "./code.js";

export {
  addWave,
  setWaveMilestones,
  addDiagram,
  setDiagram,
  addDiagramNode,
  addDiagramEdge,
  setReadmeEntry,
} from "./structure.js";
