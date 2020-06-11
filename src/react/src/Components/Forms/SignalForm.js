import React from "react";
import {FormController, FormField} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, smallerThan, notEmpty} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";

class SignalForm extends React.Component {
    constructor(props) {
        super(props);
        this.formController = React.createRef();
    }

    handleAddition = (e, { value }) => {
        this.setState((prevState) => ({
          channelOptions: [value, ...prevState.channelOptions],
        }))
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        this.formController.current.setValidating()
        if (this.formController.current.state.isValid) {
            this.props.updateParentState(this.formController.current.state.values)
            this.props.nextStep()
        }
    }

    setForms(values) {
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
                errFunc: checkForErrors(isNumber, notEmpty),
                linkedErrors: {
                    mass2: (val) => checkForErrors(smallerThan(val, 'Mass 1'), isNumber, notEmpty)
                },
                visible: formToggle === 1
            },

            {
                label: 'Mass 2 (M\u2299)',
                name: 'mass2',
                form: <Form.Input placeholder="25.0"/>,
                errFunc: checkForErrors(smallerThan(values.mass1, 'Mass 1'), isNumber, notEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Luminosity Distance (Mpc)',
                name: 'luminosityDistance',
                form: <Form.Input placeholder="2000"/>,
                errFunc: checkForErrors(isNumber, notEmpty),
                visible: formToggle === 1
            },

            {
                label: 'psi',
                name: 'psi',
                form: <Form.Input placeholder="0.4"/>,
                errFunc: checkForErrors(isNumber, notEmpty),
                visible: formToggle === 1
            },

            {
                label: 'iota',
                name: 'iota',
                form: <Form.Input placeholder="2.659"/>,
                errFunc: checkForErrors(isNumber, notEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Phase',
                name: 'phase',
                form: <Form.Input placeholder="1.3"/>,
                errFunc: checkForErrors(isNumber, notEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Merger Time (GPS Time)',
                name: 'mergerTime',
                form: <Form.Input placeholder="1126259642.413"/>,
                errFunc: checkForErrors(isNumber, notEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Right Ascension (radians)',
                name: 'ra',
                form: <Form.Input placeholder="1.375"/>,
                errFunc: checkForErrors(isNumber, notEmpty),
                visible: formToggle === 1
            },

            {
                label: 'Declination (degrees)',
                name: 'dec',
                form: <Form.Input placeholder="-1.2108"/>,
                errFunc: checkForErrors(isNumber, notEmpty),
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
        var initialData = {
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

        initialData = (this.props.data !== null) ? this.props.data : initialData
        initialData = (this.props.state !== null) ? this.props.state : initialData

        return (
            <React.Fragment>
                <FormController
                    initialValues={initialData}
                    ref={this.formController}
                >
                    {
                        props => {
                            return (
                                <Grid.Row>
                                    <Grid.Column width={10}>
                                        <Form>
                                            <Grid textAlign='left'>
                                                {
                                                    this.setForms(props.values).map(
                                                        (form, index) => (<FormField key={index} {...form}/>)
                                                    )
                                                }
                                            </Grid>
                                        </Form>
                                    </Grid.Column>
                                </Grid.Row>
                            )
                        }
                    }
                </FormController>
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

