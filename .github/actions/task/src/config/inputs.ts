/**
 * Reading of the action's inputs.
 *
 * The single place in the codebase that calls `core.getInput`, so the rest of
 * the code depends on the `ActionInputs` shape instead of on the Actions
 * runtime.
 */

import * as core from "@actions/core";

import { ActionInputs } from "../models/action-inputs";

/**
 * Read every input declared in `action.yml`.
 *
 * @throws Error when a required input is missing.
 * @returns The populated inputs.
 */
export function readInputs(): ActionInputs {
  return {
    token: core.getInput("token", { required: true }),
  };
}
