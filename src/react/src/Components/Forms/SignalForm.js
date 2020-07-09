import React from "react";
import {Form} from "semantic-ui-react";
import BaseForm from "./BaseForm";
import {checkForErrors, isANumber, isSmallerThan, isNotEmpty} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";

class SignalForm extends React.Component {
    constructor(props) {
        super(props);

        this.initialData = {
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
        
        this.initialData = (this.props.data !== null) ? this.props.data : this.initialData
        this.initialData = (this.props.state !== null) ? this.props.state : this.initialData

    }

    setForms = (values) => {
        const signalOptions = [
            {key: 'binaryBlackHole', text: 'Binary Black Hole', value: 'binaryBlackHole'},
            {key: 'binaryNeutronStar', text: 'Binary Neutron Star', value: 'binaryNeutronStar'},
        ]

        const signalInjectOptions = this.props.openData ? [{key: 'none', text: 'None', value: 'none'}].concat(signalOptions) : signalOptions
        const formToggle = ['none', 'binaryBlackHole', 'binaryNeutronStar'].indexOf(values.signalChoice)

        const forms = [
            {
                label: 'Signal Inject',
                name: 'signalChoice',
                form: <Form.Select placeholder="Select Signal Type" options={signalInjectOptions}/>
            },

            {
                label: 'Signal Params Under Construction',
                name: '',
                form: <Form.Input placeholder="Under Construction" disabled/>
            },

            {
                label: 'Mass 1 (M\u2299)',
                name: 'mass1',
                form: <Form.Input placeholder="30.0"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                linkedErrors: {
                    mass2: (val) => checkForErrors(isSmallerThan(val, 'Mass 1'), isANumber, isNotEmpty)
                },
                visible: formToggle === 1
            },

            {
                label: 'Mass 2 (M\u2299)',
                name: 'mass2',
                form: <Form.Input placeholder="25.0"/>,
                errFunc: checkForErrors(isSmallerThan(values.mass1, 'Mass 1'), isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Luminosity Distance (Mpc)',
                name: 'luminosityDistance',
                form: <Form.Input placeholder="2000"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'psi',
                name: 'psi',
                form: <Form.Input placeholder="0.4"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'iota',
                name: 'iota',
                form: <Form.Input placeholder="2.659"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Phase',
                name: 'phase',
                form: <Form.Input placeholder="1.3"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Merger Time (GPS Time)',
                name: 'mergerTime',
                form: <Form.Input placeholder="1126259642.413"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Right Ascension (radians)',
                name: 'ra',
                form: <Form.Input placeholder="1.375"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Declination (degrees)',
                name: 'dec',
                form: <Form.Input placeholder="-1.2108"/>,
                errFunc: checkForErrors(isANumber, isNotEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Same Signal for Model',
                name: 'sameSignal',
                form: <Form.Checkbox/>,
                visible: formToggle !== 0,
                valFunc: (val) => val ? {signalModel: values.signalChoice} : {}
            },

            {
                label: 'Signal Model',
                name: 'signalModel',
                form: <Form.Select placeholder="Select Signal Model" options={signalOptions}/>,
                visible: ((this.props.openData && formToggle===0) || (formToggle>0 && !values.sameSignal))
            }
        ]
        
        return forms
    }

    render() {
        return (
            <BaseForm
                initialData={this.initialData}
                setForms={this.setForms}
                prevStep={this.props.prevStep}
                nextStep={this.props.nextStep}
                updateParentState={this.props.updateParentState}
            />
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

