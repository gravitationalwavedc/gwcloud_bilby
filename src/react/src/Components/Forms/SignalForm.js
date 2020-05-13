import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, smallerThan, notEmpty} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";


class SignalForm extends React.Component {
    constructor(props) {
        super(props);
        const initialData = {
            signalChoice: 'binaryBlackHole',
            signalModel: '',
            mass1: '',
            mass2: '',
            luminosityDistance: '',
            psi: '',
            iota: '',
            phase: '',
            mergerTime: '',
            ra: '',
            dec: '',
            sameSignal: true
        }

        const errors = {}
        Object.keys(initialData).map((key) => {
            errors[key] = []
        })

        var data = (this.props.data !== null) ? this.props.data : initialData
        data = (this.props.state !== null) ? this.props.state : data

        const toggles = {
            openData: this.props.dataChoice == 'open',
            bbhToggle: initialData.signalChoice == 'binaryBlackHole'
        }
        this.state = {
            data: data,
            errors: errors,
            validate: false,
            toggles: toggles
        }
    }

    setForms = ({openData, bbhToggle}) => {
        const signalOptions = [
            {key: 'binaryBlackHole', text: 'Binary Black Hole', value: 'binaryBlackHole'},
            {key: 'binaryNeutronStar', text: 'Binary Neutron Star', value: 'binaryNeutronStar'},
            ]
        const signalInjectOptions = openData ? [{key: 'none', text: 'None', value: 'none'}].concat(signalOptions) : signalOptions

        this.forms = [
            {label: 'Signal Inject', name: 'signalChoice', form: <Form.Select placeholder="Select Signal Type" options={signalInjectOptions}/>},
            {label: 'Signal Params Under Construction', name: '', form: <Form.Input placeholder="Under Construction" disabled/>}
        ]
        if (bbhToggle) {
            this.forms.push(
                {label: 'Mass 1 (M\u2299)', name: 'mass1', form: <Form.Input  placeholder="2.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'Mass 2 (M\u2299)', name: 'mass2', form: <Form.Input  placeholder="1.0"/>, errFunc: checkForErrors(smallerThan(this.state.data.mass1, 'Mass 1'), isNumber, notEmpty)},
                {label: 'Luminosity Distance (Mpc)', name: 'luminosityDistance', form: <Form.Input  placeholder="1.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'psi', name: 'psi', form: <Form.Input placeholder="1.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'iota', name: 'iota', form: <Form.Input placeholder="1.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'Phase', name: 'phase', form: <Form.Input placeholder="1.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'Merger Time (GPS Time)', name: 'mergerTime', form: <Form.Input placeholder="1.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'Right Ascension (radians)', name: 'ra', form: <Form.Input placeholder="1.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'Declination (degrees)', name: 'dec', form: <Form.Input  placeholder="1.0"/>, errFunc: checkForErrors(isNumber, notEmpty)},
                {label: 'Same Signal for Model', name: 'sameSignal', form: <Form.Checkbox/>}
            )
        }
        if ((openData && !bbhToggle) || (bbhToggle && !this.state.data.sameSignal)) {
            this.forms.push({label: 'Signal Model', name: 'signalModel', form: <Form.Select placeholder="Select Signal Model" options={signalOptions}/>})
        }
    }

    handleChange = ({name, value, errors}) => {
        const bbhToggle = name === 'signalChoice' ? value === 'binaryBlackHole' : this.state.data.signalChoice === 'binaryBlackHole'
        this.setState(prevState => ({
            data: {
                ...prevState.data,
                [name]: value,
            },
            errors: {
                ...prevState.errors,
                [name]: errors
            },
            toggles: {
                ...prevState.toggles,
                bbhToggle: bbhToggle
            }
        })) 
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
            if (this.state.data.sameSignal) {
                const data = {
                    ...this.state.data,
                    signalModel: this.state.data.signalChoice
                }
                this.props.updateParentState(data)
            } else {
                this.props.updateParentState(this.state.data)
            }
            this.props.nextStep()
        }
    }

    render() {
        const {data, errors, toggles} = this.state
        this.setForms(toggles)
        return (
            <React.Fragment>
                <BaseForm data={data} errors={errors} forms={this.forms} onChange={this.handleChange} validate={this.state.validate}/>
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        <Button onClick={this.prevStep}>Back</Button>
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Save and Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default createFragmentContainer(SignalForm, {
    data: graphql`
        fragment SignalForm_data on SignalType {
            signalChoice
            signalModel
            mass1
            mass2
            luminosityDistance
            psi
            iota
            phase
            mergerTime
            ra
            dec
        }
    `
});

