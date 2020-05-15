import React from "react";
import {Grid, Segment, Button} from "semantic-ui-react";
import Link from 'found/lib/Link';
import BilbyBasePage from "./BilbyBasePage";

class BilbyHomePage extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: null
        }
    }

    render() {
        return (
            <BilbyBasePage loginRequired title="Welcome to Bilby" {...this.routing}>
                <Grid.Row>
                    <Segment>
                        Welcome to Bilby!
                    </Segment>
                </Grid.Row>
                <Grid.Row>
                    <Link to={'/bilby/job-form/'} exact {...this.props}>
                        <Button>Create new job</Button>
                    </Link>
                    <Link to={'/bilby/job-list/'} exact {...this.props}>
                        <Button>Job list</Button>
                    </Link>
                </Grid.Row>
            </BilbyBasePage>
        )
    }
}

export default BilbyHomePage;
