import React from "react";
import {Form, Divider, Grid, Label} from "semantic-ui-react";
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
import {assembleErrorString} from "../Utils/errors";



function BaseForm({forms, validate, onChange}) {
    const form_arr = forms.map((form, index) => <FormRow key={index} rowName={form.rowName} children={form.form} errors={form.errors} validate={validate} onChange={onChange}/>)

    return (
        <Grid.Row>
            <Grid.Column width={8}>
                <Grid divided='vertically' textAlign='left'>
                    {form_arr}
                </Grid>
            </Grid.Column>
        </Grid.Row>

    )
}

function PriorsBaseForm({forms, validate, onChange}) {
    const form_arr = forms.map((form, index) => <PriorsFormRow key={index} title={form.title} data={form.data} onChange={onChange(form.name)}/>)

    return (
        <Grid.Row>
            <Grid.Column width={8}>
                <Grid textAlign='left'>
                    {form_arr}
                </Grid>
            </Grid.Column>
        </Grid.Row>
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
    let formHasError = false
    if (props.errors && props.errors.length && props.validate) {
        formHasError = true
    }
    return (
        <Grid.Row columns={3}>
            <Grid.Column width={4}>
                {props.rowName}
            </Grid.Column>
            <Grid.Column width={8}>
                <Form>
                    {React.Children.map(props.children, (child => React.cloneElement(child, {onChange: props.onChange, error: formHasError})))}
                </Form>
            </Grid.Column>
            <Grid.Column width={4}>
                {formHasError ? <Label basic pointing='left' color='red' content={assembleErrorString(props.errors)}/> : null}
            </Grid.Column>
        </Grid.Row>
    )

}

// const PriorsForm = ({handleChange, formVals}) => {
//     const {mass1, mass2, luminosityDistance, iota, psi, phase, mergerTime, ra, dec} = formVals
//     return (
//         <PriorsBaseForm onChange={handleChange}
//             forms={[
//                 {title: 'Mass 1 (M\u2299)', name: 'mass1', data: mass1},
//                 {title: 'Mass 2 (M\u2299)', name: 'mass2', data: mass2},
//                 {title: 'Luminosity Distance (Mpc)', name: 'luminosityDistance', data: luminosityDistance},
//                 {title: 'iota', name: 'iota', data: iota},
//                 {title: 'psi', name: 'psi', data: psi},
//                 {title: 'Phase', name: 'phase', data: phase},
//                 {title: 'Merger Time (GPS Time)', name: 'mergerTime', data: mergerTime},
//                 {title: 'Right Ascension (Radians)', name: 'ra', data: ra},
//                 {title: 'Declination (Degrees)', name: 'dec', data: dec}
//             ]}
//         />
//     )
// }

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
    SamplerForm,
    SubmitForm,
    BaseForm,
    PriorsBaseForm
};