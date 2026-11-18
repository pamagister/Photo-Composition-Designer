(function () {
  const input = document.getElementById("source-path");
  const datalist = document.getElementById("source-directories");
  if (!input || !datalist) {
    return;
  }

  let timer = null;

  async function updateSuggestions() {
    const path = input.value.trim() || "~";
    try {
      const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      datalist.replaceChildren();
      for (const entry of data.directories) {
        const option = document.createElement("option");
        option.value = entry.path;
        datalist.appendChild(option);
      }
    } catch (error) {
      // Suggestions are optional; manual path entry remains available.
    }
  }

  input.addEventListener("input", () => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(updateSuggestions, 250);
  });
  input.addEventListener("focus", updateSuggestions);
})();