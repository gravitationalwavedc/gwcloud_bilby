import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, longerThan, shorterThan} from "../../Utils/errors";


class StartForm extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            data: {
                name: '',
                description: '',
            },

            errors: {
                name: [],
                description: []
            },

            validate: false
        }
        this.state.data = this.props.state === null ? this.state.data : this.props.state
    }

    handleChange = (e, data) => {
        this.setState({
            ...this.state,
            data: {
                ...this.state.data,
                [data.name]: data.value,
            },
        })
    }

    checkErrors = (name, value) => {
        let errors = []
        switch (name) {
            case 'name':
                errors = checkForErrors(longerThan(5))(value)
                break;
            case 'description':
                errors = checkForErrors(shorterThan(200))(value)
                break;
        }
        return errors;
    }

    handleErrors = () => {
        let {data, errors} = this.state
        for (const [name, val] of Object.entries(data)) {
            errors[name] = this.checkErrors(name, val)
        }
        this.setState({
            ...this.state,
            errors: errors
        })
    }

    nextStep = () => {
        this.handleErrors()
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
                <BaseForm onChange={this.handleChange} validate={this.state.validate}
                    forms={[
                        {rowName: "Job Name", form: <Form.Input name='name' placeholder="Job Name" value={data.name}/>, errors: errors.name},
                        {rowName: "Job Description", form: <Form.TextArea name='description' placeholder="Job Description" value={data.description}/>, errors: errors.description}
                    ]}
                />
                <Grid.Row columns={2}>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default StartForm;