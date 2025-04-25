
// --- Toggle Code/Content View ---
document.addEventListener('click', function(event) {
    if (event.target.matches('.toggle-button')) {
        const targetId = event.target.getAttribute('data-target');
        const targetElement = document.getElementById(targetId);
        if (targetElement) {
            targetElement.classList.toggle('hidden');
            event.target.textContent = targetElement.classList.contains('hidden') ? 'Show Code View' : 'Hide Code View';
             // Adjust button text based on what it toggles
             if(targetId.startsWith('raw-llm-')) {
                 event.target.textContent = targetElement.classList.contains('hidden') ? 'Show Raw LLM Response' : 'Hide Raw LLM Response';
             } else {
                 event.target.textContent = targetElement.classList.contains('hidden') ? 'Show Code View' : 'Hide Code View';
             }
        }
    }
});

// --- Sidebar Navigation: Smooth Scroll and Active Link Highlighting ---
function setupNavigation() {
    const sidebarLinks = document.querySelectorAll('.sidebar a');
    const contentSections = document.querySelectorAll('.content .file-details');
    const contentContainer = document.querySelector('.content'); // Get the scrollable content area

    if (!contentContainer) return; // Exit if content area not found

    // Function to remove active class from all links
    const removeActiveClasses = () => {
        sidebarLinks.forEach(link => link.classList.remove('active'));
    };

    // Smooth scroll on link click
    sidebarLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault(); // Prevent default anchor jump
            const targetId = this.getAttribute('href').substring(1);
            const targetElement = document.getElementById(targetId);

            if (targetElement) {
                // Scroll the content container, not the window
                contentContainer.scrollTo({
                    top: targetElement.offsetTop - contentContainer.offsetTop - 10, // Adjust offset as needed
                    behavior: 'smooth'
                });

                // Update active link immediately on click
                removeActiveClasses();
                this.classList.add('active');
            }
        });
    });

    // Highlight active link based on scroll position in the content container
    const observerOptions = {
        root: contentContainer, // Observe intersection within the content container
        rootMargin: '0px 0px -60% 0px', // Trigger when section is near the top
        threshold: 0 // Trigger as soon as any part is visible within margin
    };

    const observerCallback = (entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                const correspondingLink = document.querySelector(`.sidebar a[href="#${id}"]`);
                if (correspondingLink) {
                    removeActiveClasses();
                    correspondingLink.classList.add('active');
                }
            }
        });
    };

    const observer = new IntersectionObserver(observerCallback, observerOptions);

    contentSections.forEach(section => {
        observer.observe(section);
    });
}

// --- Run initializations ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed"); // <-- Add log
    // highlight.js should be called separately if needed after dynamic content loading
    // hljs.highlightAll(); // Called from HTML script tag already

    // initializeTree();
    setupNavigation();
});