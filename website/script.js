(() => {
  const gameFrame = document.getElementById("godot-game");
  const reloadButton = document.getElementById("back-to-design");

  if (!gameFrame || !reloadButton) {
    console.error("Mission Design: the game frame or reload button is missing.");
    return;
  }

  // Open the Godot export immediately: its configured Main Scene is the first game page.
  gameFrame.src = "../game/index.html";

  // Keep the workshop on screen and allow a quick restart without returning to a splash page.
  reloadButton.addEventListener("click", () => {
    gameFrame.src = "../game/index.html";
  });
})();
