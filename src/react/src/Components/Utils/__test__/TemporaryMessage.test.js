// Set the harnessApi
import React from "react";
import { expect } from "@jest/globals";
import { render, cleanup, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import TemporaryMessage from "../TemporaryMessage";

const testMessage = 'Test Message'
function setup() {

    jest.useFakeTimers()

    const { rerender } = render(<TemporaryMessage success={false} content={testMessage} icon='save' timeout={1000}/>)
    const hiddenMessage = screen.queryByText(testMessage)
    
    rerender(<TemporaryMessage success={true} content={testMessage} icon='save' />)
    const visibleMessage = screen.queryByText(testMessage)
    
    return {
        hiddenMessage,
        visibleMessage
    }
}

// These tests are kind of garbage
describe('Temporary Message', () => {
    let fields
    beforeAll(() => { fields = setup() })
    afterAll(cleanup)
    
    it('is not displayed by default', () => {
        expect(fields.hiddenMessage).not.toBeInTheDocument()
    })

    it('appears when the props are changed', () => {
        expect(fields.visibleMessage).toBeInTheDocument()
    })

    it('disappears after timeout length', () => {
        expect(fields.visibleMessage).toBeInTheDocument()
        act(() => jest.runAllTimers())
        expect(fields.visibleMessage).not.toBeInTheDocument()
    })
})