document.addEventListener("DOMContentLoaded", function() {
    // Create the nav element
    const nav = document.createElement('nav');
    nav.className = 'main-navbar';

    nav.innerHTML = `
        <div class="nav-container">
            <a href="menu.html" class="nav-logo">
                <i class="fas fa-heartbeat"></i> <span>SmartBreathing</span>
            </a>
            <button class="nav-toggle" aria-label="Abrir menú">
                <i class="fas fa-bars"></i>
            </button>
            <ul class="nav-links">
                <li><a href="menu.html"><i class="fas fa-home"></i> Inicio</a></li>
                <li><a href="index.html"><i class="fas fa-chart-line"></i> Dashboard</a></li>
                <li><a href="nuevo_usuario_paso1.html"><i class="fas fa-user-plus"></i> Registro</a></li>
                <li><a href="login.html"><i class="fas fa-sign-in-alt"></i> Login</a></li>
            </ul>
        </div>
    `;

    // Inject into the body
    document.body.prepend(nav);

    // Mobile menu toggle logic
    const toggleBtn = nav.querySelector('.nav-toggle');
    const navLinks = nav.querySelector('.nav-links');

    toggleBtn.addEventListener('click', () => {
        navLinks.classList.toggle('active');
    });

    // Highlight current page
    const currentPath = window.location.pathname.split('/').pop() || 'index.html';
    const links = nav.querySelectorAll('.nav-links a');
    links.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
});
