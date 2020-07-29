import React from "react";
import { setHarnessApi } from "./index";
import { render } from '@testing-library/react';
import { createMockEnvironment } from "relay-test-utils";
import { QueryRenderer } from 'react-relay';


global.queryRendererSetup = (inputQuery, componentToRender) => {
    setHarnessApi({
        getEnvironment: name => {
            return createMockEnvironment();
        },
        currentUser: {
            userId: 1
        }
    })

    const environment = createMockEnvironment()

    render(
        <QueryRenderer
            environment={environment}
            query={inputQuery}
            variables={{}}
            render={({ error, props }) => {
                if (props) {
                    return componentToRender(props);
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    )
    return environment
}