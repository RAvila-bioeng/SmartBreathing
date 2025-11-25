
document.addEventListener("DOMContentLoaded", function() {
  const navHtml = `
    <nav class="main-nav">
      <div class="logo"><i class="fa-solid fa-spa"></i> SmartBreathing</div>
      <ul>
        <li><a href="menu.html" id="nav-menu"><i class="fas fa-home"></i> Inicio</a></li>
        <li><a href="nuevo_usuario_paso1.html" id="nav-users"><i class="fas fa-users"></i> Usuarios</a></li>
        <li><a href="index.html" id="nav-dashboard"><i class="fas fa-chart-bar"></i> Dashboard</a></li>
      </ul>
    </nav>
  `;

  // Insert the nav bar at the beginning of the body
  document.body.insertAdjacentHTML('afterbegin', navHtml);

  // Set the active link based on the current page
  const currentPage = window.location.pathname.split("/").pop();
  if (currentPage.includes("menu")) {
    document.querySelector("#nav-menu").parentElement.classList.add("active");
  } else if (currentPage.includes("nuevo_usuario")) {
    document.querySelector("#nav-users").parentElement.classList.add("active");
  } else if (currentPage.includes("index")) {
    document.querySelector("#nav-dashboard").parentElement.classList.add("active");
  }
});
