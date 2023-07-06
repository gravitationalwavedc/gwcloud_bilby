import React from 'react';
import { RedirectException } from 'found';
import { expect } from '@jest/globals';
import { render } from '@testing-library/react';
import { handlePrivateRender, handlePublicRender } from '../routeHandlers';
import { setHarnessApi } from '../index';

describe('route handler functions', () => {
    const TestComponent = () => <h1>Test</h1>;
    const props = {
        Component: TestComponent,
        props: {
            match: {
                location: {
                    pathname: '/',
                },
            },
            location: () => {},
        },
        match: {
            location: {
                pathname: '/',
            },
        },
    };

    it('should redirect unathenticated users accessing a private route', () => {
        expect.hasAssertions();
        setHarnessApi({ hasAuthToken: () => false });
        // This is the way to catch errors in jest.
        const wrap = () => handlePrivateRender(props);
        expect(wrap).toThrow(RedirectException);
    });

    it('should allow unathenticated users to access public routes', () => {
        expect.hasAssertions();
        setHarnessApi({ hasAuthToken: () => false });

        const { getByText } = render(handlePublicRender(props));
        expect(getByText('Test')).toBeInTheDocument();
    });

    it('should recover from the match undefined bug', () => {
        expect.hasAssertions();
        const badProps = {
            Component: TestComponent,
            props: {
                location: {
                    pathname: '/',
                },
            },
        };
        const { getByText } = render(handlePublicRender(badProps));
        expect(getByText('Test')).toBeInTheDocument();
    });

    it('should display loading if the component or props have not resolved', () => {
        expect.hasAssertions();
        setHarnessApi({ hasAuthToken: () => false });
        // This is the way to catch errors in jest.
        const wrap = () => handlePublicRender(props);
        expect(wrap).not.toThrow(RedirectException);

        const { getByText } = render(handlePublicRender({ props: undefined, Component: undefined }));
        expect(getByText('Loading...')).toBeInTheDocument();
    });
});
