import React from "react";
import {PriorsBaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, smallerThan} from "../Utils/errors";



class PriorsForm extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            data: {
                mass1: {type: 'fixed', value: '', min: '', max: ''},
                mass2: {type: 'fixed', value: '', min: '', max: ''},
                luminosityDistance: {type: 'fixed', value: '', min: '', max: ''},
                iota: {type: 'fixed', value: '', min: '', max: ''},
                psi: {type: 'fixed', value: '', min: '', max: ''},
                phase: {type: 'fixed', value: '', min: '', max: ''},
                mergerTime: {type: 'fixed', value: '', min: '', max: ''},
                ra: {type: 'fixed', value: '', min: '', max: ''},
                dec: {type: 'fixed', value: '', min: '', max: ''}
            },

            errors: {
                mass1: [],
                mass2: [],
                luminosityDistance: [],
                psi: [],
                iota: [],
                phase: [],
                mergerTime: [],
                ra: [],
                dec: [],
            },

            validate: false
        }
        this.state.data = this.props.state === null ? this.state.data : this.props.state
    }

    handleChange = (e, data) => {
        const errors = this.handleErrors(data)
        this.setState({
            ...this.state,
            data: {
                ...this.state.data,
                [data.name]: data.type === "checkbox" ? data.checked : data.value,
            },
            errors: errors
        })
        console.log(this.state)
    }

    handleErrors = (data) => {
        let {errors} = this.state
        return errors;
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        const notEmpty = (arr) => {return Boolean(arr && arr.length)}
        if (Object.values(this.state.errors).some(notEmpty)) {
            this.setState({
              ...this.state,
              validate: true  
            })
        } else {
            this.props.updateParentState(this.state.data)
            this.props.nextStep()
        }
    }

    render() {
        const {data, errors} = this.state
        return (
            <React.Fragment>
                <PriorsBaseForm onChange={this.handleChange} validate={this.state.validate}
                    forms={[
                        {title: 'Mass 1 (M\u2299)', name: 'mass1', data: data.mass1},
                        {title: 'Mass 2 (M\u2299)', name: 'mass2', data: data.mass2},
                        {title: 'Luminosity Distance (Mpc)', name: 'luminosityDistance', data: data.luminosityDistance},
                        {title: 'iota', name: 'iota', data: data.iota},
                        {title: 'psi', name: 'psi', data: data.psi},
                        {title: 'Phase', name: 'phase', data: data.phase},
                        {title: 'Merger Time (GPS Time)', name: 'mergerTime', data: data.mergerTime},
                        {title: 'Right Ascension (Radians)', name: 'ra', data: data.ra},
                        {title: 'Declination (Degrees)', name: 'dec', data: data.dec}
                    ]}
                />
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        <Button onClick={this.prevStep}>Back</Button>
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default PriorsForm;