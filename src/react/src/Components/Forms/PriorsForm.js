import React from "react";
import {Form} from "semantic-ui-react";
import BaseForm from "./BaseForm";

import { graphql, createFragmentContainer } from "react-relay";
import { mergeUnlessNull } from "../../Utils/utilMethods";

class PriorsForm extends React.Component {
    constructor(props) {
        super(props);

        this.initialData = mergeUnlessNull(
            {
                priorChoice: '4s'
            },
            this.props.data,
            this.props.state
        )
    }

    setForms = (values) => {
        const forms = [
            {
                label: 'Default Prior',
                name: 'priorChoice',
                form: <Form.Select placeholder="Select Default Prior" options={
                    [
                        {key: 'high_mass', text: 'High mass', value: 'high_mass'},
                        {key: '4s', text: '4s', value: '4s'},
                        {key: '8s', text: '8s', value: '8s'},
                        {key: '16s', text: '16s', value: '16s'},
                        {key: '32s', text: '32s', value: '32s'},
                        {key: '64s', text: '64s', value: '64s'},
                        {key: '128s', text: '128s', value: '128s'},
                        {key: '128s_tidal', text: '128s tidal', value: '128s_tidal'},
                    ]
                }/>
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

export default createFragmentContainer(PriorsForm, {
    data: graphql`
        fragment PriorsForm_data on PriorType {
            priorChoice
        }
    `
});