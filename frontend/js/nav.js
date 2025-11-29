document.addEventListener("DOMContentLoaded", function() {
    // Create the nav element
    const nav = document.createElement('nav');
    nav.className = 'main-navbar';
    
    // Check auth for Dashboard link
    const userId = localStorage.getItem('user_id');
    const dashboardLink = userId ? 'index.html' : 'login.html';
    
    nav.innerHTML = `
        <div class="nav-container">
            <a href="menu.html" class="nav-logo">
                <i class="fa-solid fa-spa"></i> <span>SmartBreathing</span>
            </a>
            <button class="nav-toggle" aria-label="Abrir menú">
                <i class="fas fa-bars"></i>
            </button>
            <ul class="nav-links">
                <li><a href="menu.html"><i class="fas fa-home"></i> Inicio</a></li>
                <li><a href="${dashboardLink}" id="dashboard-nav-link"><i class="fas fa-chart-line"></i> Dashboard</a></li>
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
        // Simple exact match or fallback for root
        const href = link.getAttribute('href');
        if (href === currentPath) {
            link.classList.add('active');
        }
    });

    // Enforce Dashboard Login Requirement on Click
    const dashLinkEl = document.getElementById('dashboard-nav-link');
    if (dashLinkEl) {
        dashLinkEl.addEventListener('click', function(e) {
            if (!localStorage.getItem('user_id')) {
                // If not logged in, force to login.html even if href was set
                // (Though href is already set to login.html above, this is double safety)
                e.preventDefault();
                window.location.href = 'login.html';
            }
        });
    }
});
