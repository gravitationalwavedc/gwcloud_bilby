import React from "react";
import {Form, TextArea, Grid} from "semantic-ui-react";

function BaseForm(props) {
    const forms = props.forms
    const form_arr = forms.map((form, index) => <FormRow key={index} rowName={form.rowName} children={form.form} onChange={props.onChange}/>)

    return(
        <Grid divided='vertically' textAlign='left'>
            {form_arr}
        </Grid>
    )
}

function FormRow(props) {
    return (
        <Grid.Row columns={2}>
            <Grid.Column>
                {props.rowName}
            </Grid.Column>
            <Grid.Column>
                <Form>
                    {React.Children.map(props.children, (child => React.cloneElement(child, {onChange: props.onChange})))}
                </Form>
            </Grid.Column>
        </Grid.Row>
    )

}

// const StartForm = ({handleChange}) => 
//     <Grid divided='vertically' textAlign='left'>
//         <FormRow rowName="Job Name">
//             <Form.Input placeholder="Job Name"/>
//         </FormRow>
//         <FormRow rowName="Job Description">
//             <Form.TextArea placeholder="Job Description"/>
//         </FormRow>
//     </Grid>

const StartForm = ({handleChange}) => 
    <BaseForm onChange={handleChange}
        forms={[
                {rowName: "Job Name", form: <Form.Input name='JobName' placeholder="Job Name"/>},
                {rowName: "Job Description", form: <Form.TextArea name='JobDescription' placeholder="Job Description"/>}
        ]}
    />

const DataForm = ({handleChange}) => 
    <BaseForm onChange={handleChange}
        forms={[
            {rowName: 'Type of Data', form: <Form.Select name='DataType' placeholder="Select Data Type" options={[
                {key: 'simulated', text: 'Simulated', value: 'simulated'},
                {key: 'open', text: 'Open', value: 'open'}
            ]}/>},
            {rowName: 'Detectors', form: [<Form.Checkbox key={1} name='Hanford' label="Hanford"/>,
                                          <Form.Checkbox key={2} name='Livingston' label="Livingston"/>,
                                          <Form.Checkbox key={3} name='Virgo' label="Virgo"/>]},
            {rowName: 'Signal Duration (s)', form: <Form.Input name='SignalDuration' placeholder='2'/>},
            {rowName: 'Sampling Frequency (Hz)', form: <Form.Input name='SamplingFrequency' placeholder='2'/>},
            {rowName: 'Start Time', form: <Form.Input placeholder='2.1'/>}

        ]}
    />


const SignalForm = ({handleChange}) => 
    <BaseForm onChange={handleChange}
        forms={[
            {rowName: 'Signal Inject', form: <Form.Select name='SignalType' placeholder="Select Signal Type" options={[
                {key: 'binarybh', text: 'Binary Black Hole', value: 'binarybh'},
            ]}/>},
            {rowName: 'Mass 1 (M\u2299)', form: <Form.Input name='mass1' placeholder="2.0"/>},
            {rowName: 'Mass 2 (M\u2299)', form: <Form.Input name='mass2' placeholder="1.0"/>},
            {rowName: 'Luminosity Distance (Mpc)', form: <Form.Input name='LuminosityDistance' placeholder="1.0"/>},
            {rowName: 'psi', form: <Form.Input name='psi' placeholder="1.0"/>},
            {rowName: 'iota', form: <Form.Input name='iota' placeholder="1.0"/>},
            {rowName: 'Phase', form: <Form.Input name='Phase' placeholder="1.0"/>},
            {rowName: 'Merger Time (GPS Time)', form: <Form.Input name='MergerTime' placeholder="1.0"/>},
            {rowName: 'Right Ascension (radians)', form: <Form.Input name='RA' placeholder="1.0"/>},
            {rowName: 'Declination (degrees)', form: <Form.Input name='Dec' placeholder="1.0"/>},
            {rowName: 'Same Signal for Model', form: <Form.Checkbox name='SameSignal'/>},
        ]}
    />

const PriorsForm = ({handleChange}) => 
    <BaseForm onChange={handleChange}
        forms={[
            {rowName: 'Type', form: <Form.Select placeholder="Select Prior Type" options={[
                {key: 'fixed', text: 'Fixed', value: 'fixed'},
                {key: 'uniform', text: 'Uniform', value: 'uniform'},
            ]}/>}
        ]}
    />

const SamplerForm = ({handleChange}) => 
    <BaseForm onChange={handleChange}
        forms={[
            {rowName: 'Sampler', form: <Form.Select name='Sampler' placeholder="Select Sampler" options={[
                {key: 'dynesty', text: 'Dynesty', value: 'dynesty'},
                {key: 'nestle', text: 'Nestle', value: 'nestle'},
                {key: 'emcee', text: 'Emcee', value: 'emcee'},
            ]}/>},
            {rowName: 'Number of Live Points', form: <Form.Input name='NumberOfPoints' placeholder='1000'/>}
        ]}
    />

const SubmitForm = () => 
    <BaseForm
        forms={[
            {rowName: 'Placeholder', form: 'Placeholder'}
        ]}
    />

export {
    StartForm,
    DataForm,
    SignalForm,
    PriorsForm,
    SamplerForm,
    SubmitForm
};