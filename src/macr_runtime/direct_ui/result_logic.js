(function (root) {
  "use strict";

  function safeFailureType(value) {
    return typeof value === "string" && /^[A-Za-z0-9_]{1,128}$/.test(value)
      ? value
      : "DirectTurnFailed";
  }

  function presentation(result) {
    if (result && result.status === "completed") {
      return {
        ok: true,
        label: result.context_warning
          ? "完成 · Context 接近上限"
          : "完整回覆已投影",
        preserveInput: false,
      };
    }
    const failure = safeFailureType(result && result.failure_type);
    return {
      ok: false,
      label: `本輪失敗 · ${failure}`,
      preserveInput: true,
    };
  }

  function defaultProvider(providers) {
    if (!Array.isArray(providers)) return null;
    for (const providerId of ["grok", "ollama_qwythos"]) {
      const item = providers.find(
        (candidate) =>
          candidate &&
          candidate.provider_id === providerId &&
          candidate.ready === true,
      );
      if (item) return providerId;
    }
    return null;
  }

  function confirmDelete(value) {
    return value === "DELETE";
  }

  root.MacrDirectResult = Object.freeze({
    presentation,
    defaultProvider,
    confirmDelete,
  });
})(globalThis);
