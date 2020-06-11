// Set the harnessApi
import React from "react";
import {expect} from "@jest/globals";
import { FormController, FormField, FormContext } from "../Forms";
import { Form, Grid } from "semantic-ui-react";
import { mount } from "enzyme";
import { checkForErrors, assembleErrorString, shorterThan } from "../../../Utils/errors";


describe('Form Controller with Form Field', () => {
    let tree = (
        <FormController
            initialValues={{test: 'Test'}}
        >
            {
                props => {
                    return (
                        <Form>
                            <Grid textAlign='left'>
                                <FormField name='test' label='Test' form={<Form.Input />} errFunc={checkForErrors(shorterThan(5))} visible={props.values.test !== 'Invisible'}/>
                            </Grid>
                        </Form>
                    )
                }
            }
        </FormController>
    )

    let mountedTree = mount(tree)
    let inputField = mountedTree.find('input')
    
    it('renders correctly', () => {
        expect(mountedTree).toMatchSnapshot();
    })

    it('places initial value in the form field', () => {
        expect(inputField.prop('value')).toBe('Test')
    })

    it('modifies FormController state on change', () => {
        inputField.instance().value = 'Testing'
        inputField.simulate('change')
        
        expect(mountedTree.state().values.test).toBe('Testing')
        expect(mountedTree.state().errors.test).toHaveLength(1)
    })

    it('displays error message when set to validate', () => {
        mountedTree.instance().setValidating()
        mountedTree.update()

        expect(mountedTree.find('Label').get(0).props.content).toBe(assembleErrorString(checkForErrors(shorterThan(5))('Testing')))
        expect(mountedTree).toMatchSnapshot()
    })
    
    it('vanishes when visible is false', () => {
        inputField.instance().value = 'Invisible'
        inputField.simulate('change')
        
        expect(mountedTree.state().visible.test).toBe(false)
        expect(mountedTree).toMatchSnapshot()
    })

})