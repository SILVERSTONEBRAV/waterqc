// Optional JS enhancements for dashboard
document.addEventListener("DOMContentLoaded", function () {
    console.log("Dashboard JS loaded");

    // Optional: Activate first tab manually if Bootstrap tabs fail to show
    const firstNamubuyaTab = document.querySelector('#namubuya-tabs .nav-link.active');
    if (firstNamubuyaTab) {
        const event = new Event('shown.bs.tab');
        firstNamubuyaTab.dispatchEvent(event);
    }

    const firstWaterLimitTab = document.querySelector('#water-limit-tabs .nav-link.active');
    if (firstWaterLimitTab) {
        const event = new Event('shown.bs.tab');
        firstWaterLimitTab.dispatchEvent(event);
    }
});
