import React from "react";
import {Form, Divider, Grid, Button} from "semantic-ui-react";
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";


function BaseForm({forms, onChange}) {
    const form_arr = forms.map((form, index) => <FormRow key={index} rowName={form.rowName} children={form.form} onChange={onChange}/>)

    return (
        <Grid divided='vertically' textAlign='left'>
            {form_arr}
        </Grid>
    )
}

function PriorsBaseForm({forms, onChange}) {
    const form_arr = forms.map((form, index) => <PriorsFormRow key={index} title={form.title} data={form.data} onChange={onChange(form.name)}/>)

    return (
        <Grid textAlign='left'>
            {form_arr}
        </Grid>
    )
}
function PriorsFormRow({title, data, onChange}) {
    const {type, value, min, max} = data
    return (
        <Grid textAlign='left'>
            <Grid.Column width={16}>
                <Divider horizontal>{title}</Divider>
            </Grid.Column>
            <Grid.Row columns={4}>
                <Grid.Column>
                    Type
                </Grid.Column>
                <Grid.Column>
                    <Form.Select name={'type'} value={type} onChange={onChange} options={[
                        {key: 'fixed', text: 'Fixed', value: 'fixed'},
                        {key: 'uniform', text: 'Uniform', value: 'uniform'},
                    ]}/>
                </Grid.Column>
            </Grid.Row>
            {type === 'fixed' ? 
                <Grid.Row columns={4}>
                    <Grid.Column>
                        Value
                    </Grid.Column>
                    <Grid.Column>
                        <Form.Input fluid name={'value'} placeholder='Hello' value={value} onChange={onChange}/>
                    </Grid.Column>
                </Grid.Row>
            :
                <Grid.Row columns={4}>
                    <Grid.Column children='Min'/>
                    <Grid.Column>
                        <Form.Input fluid name={'min'} placeholder='Hello' value={min} onChange={onChange}/>
                    </Grid.Column>
                    <Grid.Column children='Max'/>
                    <Grid.Column>
                        <Form.Input fluid name={'max'} placeholder='Hello' value={max} onChange={onChange}/>
                    </Grid.Column>
                </Grid.Row>
            }
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

const StartForm = ({handleChange, formVals}) => {
    let {jobName, jobDescription} = formVals
    return (
        <BaseForm onChange={handleChange}
            forms={[
                    {rowName: "Job Name", form: <Form.Input name='jobName' placeholder="Job Name" value={jobName}/>},
                    {rowName: "Job Description", form: <Form.TextArea name='jobDescription' placeholder="Job Description" value={jobDescription}/>}
            ]}
        />
    )
}

const DataForm = ({handleChange, formVals}) => {
    const {dataType, hanford, livingston, virgo, signalDuration, samplingFrequency, startTime} = formVals
    return (
        <BaseForm onChange={handleChange}
            forms={[
                {rowName: 'Type of Data', form: <Form.Select name='dataType' placeholder="Select Data Type" value={dataType} options={[
                    {key: 'simulated', text: 'Simulated', value: 'simulated'},
                    {key: 'open', text: 'Open', value: 'open'}
                ]}/>},
                {rowName: 'Detectors', form: [<Form.Checkbox key={1} name='hanford' label="Hanford" checked={hanford}/>,
                                            <Form.Checkbox key={2} name='livingston' label="Livingston" checked={livingston}/>,
                                            <Form.Checkbox key={3} name='virgo' label="Virgo" checked={virgo}/>]},
                {rowName: 'Signal Duration (s)', form: <Form.Input name='signalDuration' placeholder='2' value={signalDuration}/>},
                {rowName: 'Sampling Frequency (Hz)', form: <Form.Input name='samplingFrequency' placeholder='2' value={samplingFrequency}/>},
                {rowName: 'Start Time', form: <Form.Input name='startTime' placeholder='2.1' value={startTime}/>}

            ]}
        />
    )
}


const SignalForm = ({handleChange, formVals, dataType}) => {
    const {signalType, signalModel, mass1, mass2, luminosityDistance, psi, iota, phase, mergerTime, ra, dec, sameSignal} = formVals
    const noneOption = [{key: 'none', text: 'None', value: 'none'}]
    const signalOptions = [{key: 'binaryBlackHole', text: 'Binary Black Hole', value: 'binaryBlackHole'}]
    return (
        <BaseForm onChange={handleChange}
            forms={dataType == 'open' ? [
                    {rowName: 'Signal Inject', form: <Form.Select name='signalType' placeholder="Select Signal Type" value={signalType} options={noneOption}/>},
                    {rowName: 'Signal Model', form: <Form.Select name='signalModel' placeholder="Select Signal Model" value={signalModel} options={signalOptions}/>},
                ]
                : [
                    {rowName: 'Signal Inject', form: <Form.Select name='signalType' placeholder="Select Signal Type" value={signalType} options={signalOptions}/>},
                    {rowName: 'Mass 1 (M\u2299)', form: <Form.Input name='mass1' placeholder="2.0" value={mass1}/>},
                    {rowName: 'Mass 2 (M\u2299)', form: <Form.Input name='mass2' placeholder="1.0" value={mass2}/>},
                    {rowName: 'Luminosity Distance (Mpc)', form: <Form.Input name='luminosityDistance' placeholder="1.0" value={luminosityDistance}/>},
                    {rowName: 'psi', form: <Form.Input name='psi' placeholder="1.0" value={psi}/>},
                    {rowName: 'iota', form: <Form.Input name='iota' placeholder="1.0" value={iota}/>},
                    {rowName: 'Phase', form: <Form.Input name='phase' placeholder="1.0" value={phase}/>},
                    {rowName: 'Merger Time (GPS Time)', form: <Form.Input name='mergerTime' placeholder="1.0" value={mergerTime}/>},
                    {rowName: 'Right Ascension (radians)', form: <Form.Input name='ra' placeholder="1.0" value={ra}/>},
                    {rowName: 'Declination (degrees)', form: <Form.Input name='dec' placeholder="1.0" value={dec}/>},
                    {rowName: 'Same Signal for Model', form: <Form.Checkbox name='sameSignal' checked={sameSignal}/>},
                ]
            }
        />
    )
}

const PriorsForm = ({handleChange, formVals}) => {
    const {mass1, mass2, luminosityDistance, iota, psi, phase, mergerTime, ra, dec} = formVals
    return (
        <PriorsBaseForm onChange={handleChange}
            forms={[
                {title: 'Mass 1 (M\u2299)', name: 'mass1', data: mass1},
                {title: 'Mass 2 (M\u2299)', name: 'mass2', data: mass2},
                {title: 'Luminosity Distance (Mpc)', name: 'luminosityDistance', data: luminosityDistance},
                {title: 'iota', name: 'iota', data: iota},
                {title: 'psi', name: 'psi', data: psi},
                {title: 'Phase', name: 'phase', data: phase},
                {title: 'Merger Time (GPS Time)', name: 'mergerTime', data: mergerTime},
                {title: 'Right Ascension (Radians)', name: 'ra', data: ra},
                {title: 'Declination (Degrees)', name: 'dec', data: dec}
            ]}
        />
    )
}

const SamplerForm = ({handleChange, formVals}) => {
    const {sampler, number} = formVals
    return (
        <BaseForm onChange={handleChange}
            forms={[
                {rowName: 'Sampler', form: <Form.Select name='sampler' placeholder="Select Sampler" value={sampler} options={[
                    {key: 'dynesty', text: 'Dynesty', value: 'dynesty'},
                    {key: 'nestle', text: 'Nestle', value: 'nestle'},
                    {key: 'emcee', text: 'Emcee', value: 'emcee'},
                ]}/>},
                {rowName: sampler==='emcee' ? 'Number of Steps' : 'Number of Live Points', form: <Form.Input name='number' placeholder='1000' value={number}/>}
            ]}
        />
    )
}

const SubmitForm = () => 
    <React.Fragment>
        Placeholder
    </React.Fragment>

export {
    StartForm,
    DataForm,
    SignalForm,
    PriorsForm,
    SamplerForm,
    SubmitForm
};