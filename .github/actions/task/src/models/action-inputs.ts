/**
 * Data shape for the action's declared inputs.
 *
 * Kept separate from the reading logic (`config/inputs.ts`) so consumers can
 * be handed a literal in tests instead of a populated environment.
 */

/** The inputs declared in `action.yml`. */
export interface ActionInputs {
  /** Token used to read and create issue comments. */
  token: string;
}
