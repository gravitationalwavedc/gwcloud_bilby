import React from "react";
import { Form } from "semantic-ui-react";
import BaseForm from "./BaseForm";
import { checkForErrors, isLongerThan, isShorterThan, isValidJobName } from "../../Utils/errors";
import { mergeUnlessNull } from "../../Utils/utilMethods";

import { graphql, createFragmentContainer } from "react-relay";

class StartForm extends React.Component {
    constructor(props) {
        super(props);


        this.initialData = mergeUnlessNull(
            {
                name: '',
                description: '',
                private: false
            },
            this.props.data,
            this.props.state
        )
    }

    setForms = (values) => {
        return [
            {
                label: "Job Name",
                name: "name",
                form: <Form.Input placeholder="Job Name" />,
                errFunc: checkForErrors(isLongerThan(5), isValidJobName),
            },

            {
                label: "Job Description",
                name: "description",
                form: <Form.TextArea placeholder="Job Description" />,
                errFunc: checkForErrors(isShorterThan(200)),
                required: false,
            },

            {
                label: "Private Job",
                name: "private",
                form: <Form.Checkbox />,
                required: false
            },
        ]
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

export default createFragmentContainer(StartForm, {
    data: graphql`
        fragment StartForm_data on OutputStartType {
            name
            description
            private
        }
    `
});