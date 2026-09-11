document.addEventListener('DOMContentLoaded', function() {
    const treatmentPlantField = document.querySelector('#id_treatment_plant');
    const treatmentPlantPhaseField = document.querySelector('#id_treatment_plant_phase');

    if (treatmentPlantField) {
        treatmentPlantField.addEventListener('change', function() {
            const treatmentPlantId = this.value;
            fetch(`/admin/qc/qualitycontrolanalysis/treatment_plant_phases/?treatment_plant_id=${treatmentPlantId}`)
                .then(response => response.json())
                .then(data => {
                    treatmentPlantPhaseField.innerHTML = '';
                    const defaultOption = document.createElement('option');
                    defaultOption.textContent = '---------';
                    treatmentPlantPhaseField.appendChild(defaultOption);

                    data.forEach(phase => {
                        const option = document.createElement('option');
                        option.value = phase.id;
                        option.textContent = phase.name;
                        treatmentPlantPhaseField.appendChild(option);
                    });
                });
        });

        // Trigger change event to load phases when editing existing analysis
        if (treatmentPlantField.value) {
            const event = new Event('change');
            treatmentPlantField.dispatchEvent(event);
        }
    }
});
