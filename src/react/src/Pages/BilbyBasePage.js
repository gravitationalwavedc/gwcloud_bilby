import React from "react";
import {Grid, Header, Segment, Button, Menu} from "semantic-ui-react";
import Link from 'found/lib/Link';

import Breadcrumbs from "../Components/Utils/Breadcrumbs";
import {harnessApi} from "../index";

class BilbyBasePage extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router
        }
    }


    render() {
        // Make sure user is logged in. If they are not, redirect the user to the login page
        if (this.props.loginRequired && !harnessApi.currentUser) {
            this.props.router.replace("/auth/?next=" + this.props.match.location.pathname)
        }
        return (
            <React.Fragment>
                <Menu borderless size='large'>
                    <Menu.Item>
                        <Breadcrumbs size='large' paths={this.props.breadcrumbPaths} {...this.routing}/>
                    </Menu.Item>
                    <Menu.Item position='right' content={'New Job'} as={Link} to={'/bilby/job-form/'} exact={true} {...this.routing}/>
                    <Menu.Item content={'My Jobs'} as={Link} to={'/bilby/job-list/'} exact={true} {...this.routing}/>
                </Menu>
                <Grid centered textAlign='center' style={{minHeight: '100vh'}} verticalAlign='top'>
                    {this.props.children}
                </Grid>
            </React.Fragment>
        )
    }
}

export default BilbyBasePage;
