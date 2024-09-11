document.addEventListener('DOMContentLoaded', function() {
    // Add smooth scrolling to all links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();

            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Add form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            let isValid = true;
            const inputs = form.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], textarea');
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    isValid = false;
                    input.classList.add('error');
                } else {
                    input.classList.remove('error');
                }
            });

            if (!isValid) {
                event.preventDefault();
                alert('Please fill in all fields');
            }
        });
    });

    // Add character count to textarea
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        const maxLength = textarea.getAttribute('maxlength');
        if (maxLength) {
            const counter = document.createElement('div');
            counter.className = 'char-counter';
            textarea.parentNode.insertBefore(counter, textarea.nextSibling);

            textarea.addEventListener('input', function() {
                const remaining = maxLength - this.value.length;
                counter.textContent = `${remaining} characters remaining`;
            });

            // Trigger the event on page load
            textarea.dispatchEvent(new Event('input'));
        }
    });
});
