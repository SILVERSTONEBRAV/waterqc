/**
 * plant_section_user_cascade.js
 * Universal Cascading Filter Engine for Treatment Plant -> Section -> User
 * 
 * Logic:
 * 1. When a Treatment Plant is selected, filter and display only sections belonging to that plant.
 * 2. When a Section is selected, filter and display only users belonging to that section (and plant).
 * 3. Works automatically on Django Admin change forms, custom forms, and dynamic modals.
 */

(function (window, document) {
    'use strict';

    const API_ENDPOINTS = {
        plantSections: '/core/api/plant-sections/',
        sectionUsers: '/core/api/section-users/',
    };

    /**
     * Resolves matching select or input elements within a form or container.
     */
    function findCascadeTriad(container) {
        const root = container || document;

        // Find plant element
        const plantEl = root.querySelector(
            'select[name="treatment_plant"], select[name="assigned_treatment_plant"], select[id$="treatment_plant"], select[id$="assigned_treatment_plant"], select[data-cascade="plant"]'
        );

        // Find section element
        const sectionEl = root.querySelector(
            'select[name="section"], select[id$="section"], select[data-cascade="section"]'
        );

        // Find user elements (can be supervisor, user, staff, etc.)
        const userEls = root.querySelectorAll(
            'select[name="user"], select[name="staff"], select[name="supervisor"], select[id$="user"], select[id$="staff"], select[id$="supervisor"], select[data-cascade="user"]'
        );

        return { plantEl, sectionEl, userEls };
    }

    /**
     * Fetch sections for given treatment plant.
     */
    async function fetchPlantSections(plantId) {
        if (!plantId) return [];
        try {
            const url = `${API_ENDPOINTS.plantSections}?treatment_plant=${encodeURIComponent(plantId)}`;
            const res = await fetch(url, {
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            return data.sections || [];
        } catch (err) {
            console.error('[PlantSectionUserCascade] Failed to fetch sections for plant', plantId, err);
            return [];
        }
    }

    /**
     * Fetch users for given section and optional plant.
     */
    async function fetchSectionUsers(sectionId, plantId) {
        if (!sectionId) return [];
        try {
            let url = `${API_ENDPOINTS.sectionUsers}?section=${encodeURIComponent(sectionId)}`;
            if (plantId) {
                url += `&treatment_plant=${encodeURIComponent(plantId)}`;
            }
            const res = await fetch(url, {
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            return data.users || [];
        } catch (err) {
            console.error('[PlantSectionUserCascade] Failed to fetch users for section', sectionId, err);
            return [];
        }
    }

    /**
     * Repopulates a standard or Select2 HTML select dropdown with options.
     */
    function repopulateSelect(selectEl, items, selectedValue, placeholder = '---------') {
        if (!selectEl) return;

        const currentVal = selectedValue !== undefined ? selectedValue : selectEl.value;
        const fragment = document.createDocumentFragment();

        // Placeholder option
        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.textContent = placeholder;
        fragment.appendChild(emptyOption);

        let matchFound = false;
        items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.label || item.name || item.username;
            if (String(item.id) === String(currentVal)) {
                opt.selected = true;
                matchFound = true;
            }
            fragment.appendChild(opt);
        });

        selectEl.innerHTML = '';
        selectEl.appendChild(fragment);

        if (!matchFound && currentVal) {
            selectEl.value = '';
        }

        // Trigger change for UI listeners / Select2
        if (window.jQuery && window.jQuery(selectEl).data('select2')) {
            window.jQuery(selectEl).trigger('change.select2');
        } else {
            selectEl.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    /**
     * Binds cascading logic to a specific container (form or document)
     */
    function attachCascadeToForm(container) {
        const { plantEl, sectionEl, userEls } = findCascadeTriad(container);

        if (!plantEl && !sectionEl) {
            return;
        }

        // Cache initial values on load
        let initialPlantVal = plantEl ? plantEl.value : '';
        let initialSectionVal = sectionEl ? sectionEl.value : '';

        // If plant is selected, handle plant -> section cascade
        if (plantEl && sectionEl) {
            const handlePlantChange = async (isInitial = false) => {
                const plantId = plantEl.value;
                if (!plantId) {
                    repopulateSelect(sectionEl, [], '', '--------- (Select Treatment Plant first)');
                    userEls.forEach(uEl => repopulateSelect(uEl, [], '', '--------- (Select Section first)'));
                    return;
                }

                const currentSectionVal = isInitial ? initialSectionVal : sectionEl.value;
                const sections = await fetchPlantSections(plantId);
                repopulateSelect(sectionEl, sections, currentSectionVal, '--------- Select Section ---------');

                // If section was already set and remains valid, trigger its user cascade
                if (sectionEl.value) {
                    handleSectionChange(isInitial);
                } else {
                    userEls.forEach(uEl => repopulateSelect(uEl, [], '', '--------- (Select Section first)'));
                }
            };

            plantEl.addEventListener('change', () => handlePlantChange(false));
            if (window.jQuery && window.jQuery(plantEl).data('select2')) {
                window.jQuery(plantEl).on('select2:select select2:clear', () => handlePlantChange(false));
            }

            // Initial population on page load if plant is already selected
            if (initialPlantVal) {
                handlePlantChange(true);
            }
        }

        // Handle section -> users cascade
        const handleSectionChange = async (isInitial = false) => {
            if (!sectionEl || !userEls || userEls.length === 0) return;
            const sectionId = sectionEl.value;
            const plantId = plantEl ? plantEl.value : '';

            if (!sectionId) {
                userEls.forEach(uEl => {
                    repopulateSelect(uEl, [], '', '--------- (Select Section first)');
                });
                return;
            }

            const users = await fetchSectionUsers(sectionId, plantId);
            userEls.forEach(uEl => {
                const initialUserVal = isInitial ? uEl.value : uEl.value;
                repopulateSelect(uEl, users, initialUserVal, '--------- Select User ---------');
            });
        };

        if (sectionEl && userEls && userEls.length > 0) {
            sectionEl.addEventListener('change', () => handleSectionChange(false));
            if (window.jQuery && window.jQuery(sectionEl).data('select2')) {
                window.jQuery(sectionEl).on('select2:select select2:clear', () => handleSectionChange(false));
            }

            if (!plantEl && initialSectionVal) {
                handleSectionChange(true);
            }
        }
    }

    // Auto-initialize across document forms
    function initAll() {
        // Forms in page
        const forms = document.querySelectorAll('form');
        if (forms.length > 0) {
            forms.forEach(form => attachCascadeToForm(form));
        } else {
            attachCascadeToForm(document);
        }

        // Also watch for dynamically added modals or inlines
        const observer = new MutationObserver(mutations => {
            for (const mutation of mutations) {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1) { // ELEMENT_NODE
                        if (node.tagName === 'FORM' || node.classList.contains('modal') || node.classList.contains('inline-related')) {
                            attachCascadeToForm(node);
                        } else if (node.querySelector && (node.querySelector('select[name="section"]') || node.querySelector('select[name="treatment_plant"]'))) {
                            attachCascadeToForm(node);
                        }
                    }
                });
            }
        });

        observer.observe(document.body || document.documentElement, {
            childList: true,
            subtree: true
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }

    // Expose API globally
    window.PlantSectionUserCascade = {
        init: initAll,
        attach: attachCascadeToForm,
        fetchPlantSections,
        fetchSectionUsers,
    };

})(window, document);
