import React, {useState} from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, longerThan, shorterThan, nameUnique} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";

// function useFormInput(initialValue) {
//     const [value, setValue] = useState(initialValue)
    
//     function handleChange(e) {
//         setValue(e.target.value)
//     }

//     return {
//         value,
//         onChange: handleChange
//     }
// }

// function StartForm() {
//     const data = useState('a')
//     console.log(data)
//     const initialData = {
//         name: '',
//         description: ''
//     }
//     const stateErrors = {}
//     Object.keys(initialData).map((key) => {
//         stateErrors[key] = []
//     })

//     var stateData = (props.data !== null) ? props.data : initialData
//     stateData = (props.state !== null) ? props.state : stateData
//     console.log('hello', data)
//     const [errors, setErrors] = useState(stateErrors)
//     const [validate, setValidate] = useState(false)

//     // const checkErrors = (name, value) => {
//     //     let errors = []
//     //     switch (name) {
//     //         case 'name':
//     //             errors = checkForErrors(longerThan(5))(value)
//     //             break;
//     //         case 'description':
//     //             errors = checkForErrors(shorterThan(200))(value)
//     //             break;
//     //     }
//     //     return errors;
//     // }

//     // const handleErrors = () => {
//     //     let {data, errors} = this.state
//     //     for (const [name, val] of Object.entries(data)) {
//     //         errors[name] = this.checkErrors(name, val)
//     //     }
//     //     this.setState({
//     //         ...this.state,
//     //         errors: errors
//     //     })
//     // }

//     // const nextStep = () => {
//     //     this.handleErrors()
//     //     const notEmpty = (arr) => {return Boolean(arr && arr.length)}
//     //     if (Object.values(this.state.errors).some(notEmpty)) {
//     //         this.setState({
//     //           ...this.state,
//     //           validate: true  
//     //         })
//     //     } else {
//     //         this.props.updateParentState(this.state.data)
//     //         this.props.nextStep()
//     //     }
//     // }

//     return (
//         <React.Fragment>
//             <BaseForm onChange={() => {console.log('Clicked')}} validate={validate}
//                 forms={[
//                     {rowName: "Job Name", form: <Form.Input name='name' placeholder="Job Name" value={data.name}/>, errors: errors.name},
//                     {rowName: "Job Description", form: <Form.TextArea name='description' placeholder="Job Description" value={data.description}/>, errors: errors.description}
//                 ]}
//             />
//             <Grid.Row columns={2}>
//                 <Grid.Column floated='right'>
//                     <Button onClick={() => {console.log('Clicked')}}>Save and Continue</Button>
//                 </Grid.Column>
//             </Grid.Row>
//         </React.Fragment>
//     )

// }

class StartForm extends React.Component {
    constructor(props) {
        super(props);
        const initialData = {
            name: '',
            description: '',
            private: false
        }

        const errors = {}
        Object.keys(initialData).map((key) => {
            errors[key] = []
        })

        var data = (this.props.data !== null) ? this.props.data : initialData
        data = (this.props.state !== null) ? this.props.state : data
        this.state = {
            data: data,
            errors: errors,
            validate: false
        }
        this.forms = [
            {label: "Job Name", name: "name", form: <Form.Input placeholder="Job Name"/>, errFunc: checkForErrors(longerThan(5))},
            {label: "Job Description", name: "description", form: <Form.TextArea placeholder="Job Description"/>, errFunc: checkForErrors(shorterThan(200)), requiredField: false},
            {label: "Private job", name: "private", form: <Form.Checkbox />}
        ]
    }

    handleChange = ({name, value, errors}) => {
        this.setState(prevState => ({
            data: {
                ...prevState.data,
                [name]: value,
            },
            errors: {
                ...prevState.errors,
                [name]: errors
            }
        })) 
    }

    nextStep = () => {
        const notEmpty = (arr) => {return Boolean(arr && arr.length)}
        if (Object.values(this.state.errors).some(notEmpty)) {
            this.setState({
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
                <BaseForm data={data} errors={errors} forms={this.forms} onChange={this.handleChange} validate={this.state.validate}/>
                <Grid.Row columns={2}>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Save and Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default createFragmentContainer(StartForm, {
    data: graphql`
        fragment StartForm_data on OutputStartType {
            name
            description
        }
    `
});