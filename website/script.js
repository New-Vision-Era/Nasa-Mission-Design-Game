(() => {
  const homeScreen = document.getElementById("design-home");
  const gameScreen = document.getElementById("game-screen");
  const enterButton = document.getElementById("enter-workshop");
  const backButton = document.getElementById("back-to-design");
  const gameFrame = document.getElementById("godot-game");

  if (!homeScreen || !gameScreen || !enterButton || !backButton || !gameFrame) {
    console.error("Mission Design: required screen elements are missing.");
    return;
  }

  let gameLoaded = false;

  function showScreen(screen) {
    const showGame = screen === "game";
    homeScreen.classList.toggle("active", !showGame);
    gameScreen.classList.toggle("active", showGame);
    homeScreen.setAttribute("aria-hidden", String(showGame));
    gameScreen.setAttribute("aria-hidden", String(!showGame));

    if (showGame && !gameLoaded) {
      // The Godot export is kept in its own folder; load it only when requested.
      gameFrame.src = "../game/index.html";
      gameLoaded = true;
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  enterButton.addEventListener("click", () => showScreen("game"));
  backButton.addEventListener("click", () => showScreen("home"));

  // Start on the spacecraft-design portal, not directly inside the Godot export.
  showScreen("home");
})();