import React from "react";
import {FormController, FormField} from "./Forms";
import {Form, Grid, Button, Label} from "semantic-ui-react";
import {checkForErrors, longerThan, shorterThan, nameUnique, validJobName, assembleErrorString} from "../../Utils/errors";

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
        this.formController = React.createRef();
    }

    nextStep = () => {
        this.formController.current.setValidating()
        if (this.formController.current.state.isValid) {
            this.props.updateParentState(this.formController.current.state.values)
            this.props.nextStep()
        }
    }

    setForms(values) {
        return [
            {
                label: "Job Name",
                name: "name",
                form: <Form.Input placeholder="Job Name"/>,
                errFunc: checkForErrors(longerThan(5), validJobName),
            },
            
            {
                label: "Job Description",
                name: "description",
                form: <Form.TextArea placeholder="Job Description"/>,
                errFunc: checkForErrors(shorterThan(200)),
                required: false,
            },
            
            {
                label: "Private job",
                name: "private",
                form: <Form.Checkbox />,
                required: false
            },
        ]
    }

    render() {
        var initialData = {
            name: '',
            description: '',
            private: false
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
                        <Button onClick={() => this.formController.current.setValidating()}>Validate</Button>
                    </Grid.Column>
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
            private
        }
    `
});