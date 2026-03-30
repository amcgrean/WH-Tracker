/**
 * Settings modal for the dispatch console.
 */
import { on, emit, getState, saveSettings } from './dispatch-state.js';

export function init() {
  const backdrop = document.getElementById('settingsBackdrop');
  const $ = id => document.getElementById(id);

  // Open
  on('settings-open', () => {
    const s = getState().settings;
    $('settRefresh').value = s.refreshSec ?? 30;
    $('settBranch').value = s.defaultBranch || '';
    $('settBasemap').value = s.basemap || 'street';
    $('colorK').value = s.colors?.K || '#2ca02c';
    $('colorS').value = s.colors?.S || '#1f77b4';
    $('colorB').value = s.colors?.B || '#ff7f0e';
    $('colorCM').value = s.colors?.CM || '#d62728';
    backdrop.classList.add('open');
  });

  // Cancel
  $('settCancel').addEventListener('click', () => backdrop.classList.remove('open'));

  // Click outside to close
  backdrop.addEventListener('click', e => {
    if (e.target === backdrop) backdrop.classList.remove('open');
  });

  // Save
  $('settSave').addEventListener('click', () => {
    saveSettings({
      refreshSec: parseInt($('settRefresh').value) || 30,
      defaultBranch: $('settBranch').value,
      basemap: $('settBasemap').value,
      colors: {
        K: $('colorK').value,
        S: $('colorS').value,
        B: $('colorB').value,
        CM: $('colorCM').value,
      },
    });
    backdrop.classList.remove('open');
  });
}
