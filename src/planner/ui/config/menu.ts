// Koan config menu. Opens a settings-style list with config sections.
// Currently exposes one section: "Model selection".
// New sections can be added here as additional SettingItems.

import type { ExtensionCommandContext } from "@mariozechner/pi-coding-agent";
import { getSettingsListTheme } from "@mariozechner/pi-coding-agent";
import { type SettingItem, SettingsList } from "@mariozechner/pi-tui";

import { ALL_PHASE_MODEL_KEYS, type PhaseModelKey } from "../../model-phase.js";
import { loadPhaseModelConfig } from "../../model-config.js";
import { createModelSelectionComponent } from "./model-selection.js";

function configSummary(config: Record<PhaseModelKey, string> | null): string {
  if (config === null) return "inheriting active model";
  return `${ALL_PHASE_MODEL_KEYS.length} keys configured`;
}

export async function openKoanConfig(ctx: ExtensionCommandContext): Promise<void> {
  if (!ctx.hasUI) {
    ctx.ui.notify("Koan config requires an interactive terminal.", "warning");
    return;
  }

  await ctx.ui.custom<void>(async (tui, theme, _keybindings, done) => {
    const initialConfig = await loadPhaseModelConfig();
    let currentConfig = initialConfig;

    const activeModelId = ctx.model
      ? `${ctx.model.provider}/${ctx.model.id}`
      : undefined;

    // settingsList is captured in closure; submenu is only invoked after construction.
    let settingsList: SettingsList;

    const sectionItems: SettingItem[] = [
      {
        id: "model-selection",
        label: "Model selection",
        currentValue: configSummary(currentConfig),
        submenu: (_cv, submenuDone) => {
          return createModelSelectionComponent(
            tui,
            theme,
            ctx.modelRegistry,
            activeModelId,
            currentConfig,
            (newConfig) => {
              currentConfig = newConfig;
              settingsList.updateValue("model-selection", configSummary(newConfig));
            },
            (error) => {
              const message = error instanceof Error ? error.message : String(error);
              ctx.ui.notify(`Failed to save koan model config: ${message}`, "error");
            },
            () => submenuDone(undefined),
          );
        },
      },
    ];

    const returnItem: SettingItem = {
      id: "__return",
      label: "Return",
      description: "Close /koan config (same as Esc)",
      currentValue: "",
      values: [""],
    };

    const items: SettingItem[] = [...sectionItems, returnItem];

    settingsList = new SettingsList(
      items,
      20,
      getSettingsListTheme(),
      (id) => {
        if (id === "__return") done();
      },
      () => done(),
    );

    return {
      render: (w) => settingsList.render(w),
      handleInput: (d) => settingsList.handleInput(d),
      invalidate: () => settingsList.invalidate(),
    };
  });
}
